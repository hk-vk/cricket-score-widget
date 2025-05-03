# cricket_widget_fluent.py

# --- Imports ---
import sys
import time
import threading
import logging
import requests
import re
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageQt # Need ImageQt for QPixmap conversion

# PyQt5 Imports
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPoint, QSize
from PyQt5.QtGui import QIcon, QPixmap, QImage, QCursor, QFont, QColor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QSystemTrayIcon, QMenu, QAction, QDesktopWidget, 
    QSizePolicy, QHBoxLayout, QPushButton, QGraphicsDropShadowEffect
)

# Fluent Widgets Imports
from qfluentwidgets import setTheme, Theme, Flyout, FlyoutAnimationType, BodyLabel, CaptionLabel, FlyoutView, FlyoutViewBase, FlyoutAnimationManager, InfoBar, InfoBarPosition # Import necessary components

# --- Configuration ---
CRICBUZZ_URL = "https://www.cricbuzz.com/"
UPDATE_INTERVAL_SECONDS = 120  # Update homepage matches
DETAILED_UPDATE_INTERVAL_SECONDS = 15 # Update selected match score
ICON_PATH = "cricket_icon.ico"
LOG_FILE = "cricket_widget_fluent.log" # Use a new log file
MAX_MATCHES_TOOLTIP = 3 # Max matches in tooltip
MAX_MATCHES_MENU = 10 # Max matches in menu
TOOLTIP_MAX_LEN = 250 # Tooltip length limit
FLYOUT_WIDTH = 320
# FLYOUT_MAX_HEIGHT = 400 # Let height be dynamic for now

# --- Logging Setup ---
logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s')

# --- Global State (for data sharing, minimize reliance)
matches_data_cache = [] # Cache for menu building
selected_match_url_cache = None # Cache for detailed fetcher

# --- Helper Functions ---
def create_default_icon():
    """Creates a fallback QIcon using Pillow."""
    try:
        width, height = 64, 64
        # Create a simple placeholder image
        image = Image.new('RGBA', (width, height), (0, 80, 0, 200)) # Dark Green semi-transparent
        draw = ImageDraw.Draw(image)
        draw.text((width*0.3, height*0.2), "C", fill="white", font_size=36)
        logging.info("Created default fallback icon image.")
        # Convert Pillow Image to QPixmap for QIcon
        qimage = ImageQt.ImageQt(image)
        pixmap = QPixmap.fromImage(qimage)
        if pixmap.isNull():
             logging.error("Failed to convert Pillow image to QPixmap.")
             return QIcon() # Return empty icon if conversion fails
        return QIcon(pixmap)
    except Exception as e:
        logging.error(f"Could not create default fallback icon: {e}", exc_info=True)
        return QIcon() # Return empty icon on error

def format_tooltip_pyqt(matches):
    """Formats the tooltip string for QSystemTrayIcon (uses newline)."""
    if not matches:
        return "Fetching matches..."
    tooltip_parts = []
    for i, match in enumerate(matches):
        if i >= MAX_MATCHES_TOOLTIP:
            break
        title = match.get('title', 'N/A')[:60] # Limit parts
        score = match.get('score', 'N/A')[:60]
        tooltip_parts.append(f"{title}: {score}")
    if not tooltip_parts:
         return "No matches found."
    tooltip_string = "\n".join(tooltip_parts)
    if len(tooltip_string) > TOOLTIP_MAX_LEN:
        tooltip_string = tooltip_string[:TOOLTIP_MAX_LEN - 3] + "..."
    return tooltip_string

# --- Data Fetching Functions (Copied from previous version) ---
def fetch_and_parse_cricbuzz():
    # ... (Full implementation from cricket_widget.py L:49-135) ...
    logging.info("Attempting to fetch homepage matches from Cricbuzz.")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.google.com/'
    }
    live_matches_data = []
    try:
        response = requests.get(CRICBUZZ_URL, headers=headers, timeout=20)
        response.raise_for_status()
        logging.info(f"Successfully fetched Cricbuzz homepage (Status: {response.status_code}).")
        soup = BeautifulSoup(response.text, 'html.parser')
        match_ul_list = soup.find_all("ul", "cb-col cb-col-100 videos-carousal-wrapper cb-mtch-crd-rt-itm")
        if not match_ul_list:
            logging.warning("Could not find the main match list UL element using primary selector.")
            match_elements = soup.select('div.cb-mtch-crd-rt-itm')
            if not match_elements:
                 match_elements = soup.select('li[class*="cb-view-all-ga cb-match-card cb-bg-white"]')
            if match_elements:
                 logging.info("Falling back to secondary homepage selectors.")
                 for item in match_elements:
                     url_tag = item.find('a', href=True)
                     if url_tag and url_tag['href'].startswith('/live-cricket-scores/'):
                        url = 'https://www.cricbuzz.com' + url_tag['href']
                        title = url_tag.get('title', item.get_text(strip=True))[:100]
                        score_div = item.select_one('div.cb-lv-scrs-col')
                        score = score_div.get_text(strip=True)[:100] if score_div else "N/A"
                        live_matches_data.append({'title': title, 'score': score, 'url': url})
                 return live_matches_data
            else:
                 return []
        match_count = 0
        for match_ul in match_ul_list:
            for link_tag in match_ul.find_all("a", href=True):
                href = link_tag.get('href')
                title = link_tag.get('title', '').strip()[:100]
                if href and href.startswith('/live-cricket-scores/') and title:
                    url = 'https://www.cricbuzz.com' + href
                    score = "N/A"
                    score_div = link_tag.select_one('div.cb-lv-scrs-col')
                    if score_div:
                        score = score_div.get_text(separator=" ", strip=True)[:100]
                    else:
                        status_tag = link_tag.select_one('div[class*="cb-text-live"], div[class*="cb-text-complete"], span[class*="cb-text-preview"]')
                        if status_tag:
                           score = status_tag.get_text(strip=True)[:100]
                    live_matches_data.append({'title': title, 'score': score, 'url': url})
                    match_count += 1
                if match_count >= MAX_MATCHES_MENU: break
            if match_count >= MAX_MATCHES_MENU: break
        logging.info(f"Successfully parsed {len(live_matches_data)} matches from homepage.")
        return live_matches_data
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching Cricbuzz homepage: {e}")
    except Exception as e:
        logging.error(f"Error parsing Cricbuzz homepage HTML: {e}", exc_info=True)
    return []

def fetch_detailed_score(url):
    if not url: return None
    logging.info(f"Attempting to fetch detailed score from: {url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': CRICBUZZ_URL
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        title, score, status_text = "N/A", "N/A", ""
        
        # Extract title - try multiple selectors
        title_tag = soup.select_one('h1.cb-nav-hdr, div.cb-nav-main h1, div.cb-match-header h1, div.cb-schdl div.cb-font-18')
        if title_tag:
            title = title_tag.get_text(strip=True)[:150]
        else:
             html_title = soup.find('title')
             if html_title: title = html_title.text.split('|')[0].strip()[:150]
        
        # Extract main score - try multiple approaches
        score_elements = soup.select('div.cb-scrs-wrp, div.cb-mini-scr, div.cb-scrd-hdr-rw, div.cb-col-scores, div.cb-min-bat-rw')
        if score_elements:
            score_parts = [elem.get_text(strip=True) for elem in score_elements]
            score = " | ".join(filter(None, score_parts))[:150]
        else:
            # Fallback score extraction
            score_div = soup.select_one('div.cb-scr-wll-chvrn, div.cb-hmscg-bat-txt')
            if score_div:
                score = score_div.get_text(strip=True)[:150]
        
        # Extract match status
        status_selectors = [
            "div.cb-text-live", 
            "div.cb-text-complete", 
            "div.cb-text-preview",
            "div.cb-text-lunch",
            "div.cb-text-stump",
            "div.cb-text-tea",
            "div.cb-text-inprogress",
            "div.cb-text-delay",
            "div.cb-toss-sts",
            "div.cb-min-stts"
        ]
        status_tag = soup.select_one(", ".join(status_selectors))
        if status_tag: status_text = status_tag.get_text(strip=True)
        if status_text:
             if score == "N/A" or score == "": score = status_text[:150]
             elif status_text not in score: score = (score + f" ({status_text})")[:150]
        
        # Create result dictionary with basic info
        result = {'title': title, 'score': score}
        
        # Try different approaches to extract batting stats
        batsmen = []
        
        # First try the main scorecard
        batting_tables = soup.select("div.cb-ltst-wgt-hdr")
        for batting_table in batting_tables:
            # Check if this table contains batsmen
            if batting_table.select_one('.cb-scrd-itms .cb-col-25') or 'BATTING' in batting_table.get_text().upper():
                batsman_rows = batting_table.select("div.cb-scrd-itms")
                for row in batsman_rows:
                    # Skip rows that aren't batsmen (extras, total, etc)
                    if not row.select_one(".cb-col-25") or "cb-scrd-nb" in row.get("class", []):
                        continue
                    
                    # Get name, status, runs, balls, 4s, 6s, SR
                    cols = row.select("div[class*='cb-col']")
                    if len(cols) >= 7:
                        name_col = cols[0].get_text(strip=True)
                        status_col = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                        runs_col = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                        balls_col = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                        fours_col = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                        sixes_col = cols[5].get_text(strip=True) if len(cols) > 5 else ""
                        sr_col = cols[6].get_text(strip=True) if len(cols) > 6 else ""
                        
                        # Mark not out batsmen with asterisk
                        if "not out" in status_col.lower():
                            name_col += " *"
                        
                        batsmen.append({
                            'name': name_col,
                            'runs': runs_col,
                            'balls': balls_col,
                            'fours': fours_col,
                            'sixes': sixes_col,
                            'sr': sr_col
                        })
        
        # If no batsmen found, try alternative selectors for current batsmen (mini scorecard)
        if not batsmen:
            curr_batsmen_rows = soup.select("div.cb-min-bat-rw")
            for row in curr_batsmen_rows:
                name_tag = row.select_one(".cb-min-itm-bat")
                runs_tag = row.select_one(".cb-min-itm-rn")
                if name_tag and runs_tag:
                    name = name_tag.get_text(strip=True)
                    runs_info = runs_tag.get_text(strip=True)
                    
                    # Try to parse runs_info into components
                    runs = re.search(r'(\d+)', runs_info)
                    balls = re.search(r'\((\d+)\)', runs_info)
                    
                    batsmen.append({
                        'name': name + " *",  # Mark as current batsman
                        'runs': runs.group(1) if runs else "",
                        'balls': balls.group(1) if balls else "",
                        'fours': "", # Not available in mini view
                        'sixes': "", # Not available in mini view
                        'sr': ""     # Not available in mini view
                    })
        
        # Extract bowling stats - try multiple approaches
        bowlers = []
        
        # First look for the bowling section header
        bowling_headers = soup.select("div.cb-scrd-hdr-rw, div.cb-ltst-wgt-hdr")
        for header in bowling_headers:
            if 'BOWLING' in header.get_text().upper():
                # Get parent table or next sibling table
                bowling_section = header.parent or header.find_next("div", "cb-ltst-wgt-hdr")
                if bowling_section:
                    # Find all bowler rows
                    bowler_rows = bowling_section.select("div.cb-scrd-itms")
                    for row in bowler_rows:
                        cols = row.select("div[class*='cb-col']")
                        if len(cols) >= 8:
                            name_col = cols[0].get_text(strip=True)
                            overs_col = cols[1].get_text(strip=True) if len(cols) > 1 else ""
                            maidens_col = cols[2].get_text(strip=True) if len(cols) > 2 else ""
                            runs_col = cols[3].get_text(strip=True) if len(cols) > 3 else ""
                            wickets_col = cols[4].get_text(strip=True) if len(cols) > 4 else ""
                            economy_col = cols[5].get_text(strip=True) if len(cols) > 5 else ""
                            
                            # Mark current bowler with asterisk
                            is_current = False
                            current_bowler_tag = soup.select_one(".cb-min-itm-bow")
                            if current_bowler_tag and current_bowler_tag.get_text(strip=True) in name_col:
                                name_col += " *"
                                is_current = True
                                
                            # Or mark based on an incomplete over
                            if not is_current and overs_col and "." in overs_col:
                                name_col += " *"
                            
                            bowlers.append({
                                'name': name_col,
                                'overs': overs_col,
                                'maidens': maidens_col,
                                'runs': runs_col,
                                'wickets': wickets_col,
                                'economy': economy_col
                            })
        
        # If no bowlers found, try alternative selectors for current bowler (mini scorecard)
        if not bowlers:
            curr_bowler_row = soup.select_one("div.cb-min-bow-rw")
            if curr_bowler_row:
                name_tag = curr_bowler_row.select_one(".cb-min-itm-bow")
                figures_tag = curr_bowler_row.select_one(".cb-min-itm-bwl")
                if name_tag and figures_tag:
                    name = name_tag.get_text(strip=True)
                    figures = figures_tag.get_text(strip=True)
                    
                    # Try to parse bowling figures
                    overs = re.search(r'([\d\.]+)[-o]', figures, re.IGNORECASE)
                    wickets = re.search(r'(\d+)[-w]', figures, re.IGNORECASE)
                    runs = re.search(r'(\d+)[-r]', figures, re.IGNORECASE)
                    
                    bowlers.append({
                        'name': name + " *",  # Mark as current bowler
                        'overs': overs.group(1) if overs else "",
                        'maidens': "",  # Not available in mini view
                        'runs': runs.group(1) if runs else "",
                        'wickets': wickets.group(1) if wickets else "",
                        'economy': ""    # Not available in mini view
                    })
        
        # Extract match info - look for specific text patterns
        # Partnership
        partnership = ""
        partnership_elements = soup.select("div:contains('Partnership:'), span:contains('Partnership:')")
        for element in partnership_elements:
            text = element.get_text(strip=True)
            if "Partnership:" in text:
                partnership = text
                break
        
        # Last wicket
        last_wicket = ""
        wicket_elements = soup.select("div:contains('Last Wicket:'), span:contains('Last Wicket:')")
        for element in wicket_elements:
            text = element.get_text(strip=True)
            if "Last Wicket:" in text:
                last_wicket = text
                break
        
        # Toss information
        toss = ""
        toss_elements = soup.select("div.cb-toss-sts, div:contains('Toss:'), span:contains('Toss:')")
        for element in toss_elements:
            text = element.get_text(strip=True)
            if "toss" in text.lower():
                toss = text
                break
        
        # Recent overs/runs
        recent_overs = ""
        recent_elements = soup.select("div:contains('Last'), span:contains('Last')")
        for element in recent_elements:
            text = element.get_text(strip=True)
            if "Last" in text and ("overs" in text or "runs" in text):
                recent_overs = text
                break
        
        # Add detailed stats to result
        result['batsmen'] = batsmen
        result['bowlers'] = bowlers
        result['partnership'] = partnership
        result['last_wicket'] = last_wicket
        result['toss'] = toss
        result['recent_overs'] = recent_overs
        
        logging.info(f"Detailed score parsed: Title='{title}', Score='{score}'")
        if batsmen:
            logging.info(f"Found {len(batsmen)} batsmen and {len(bowlers)} bowlers")
        return result
    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching detailed score from {url}: {e}")
    except Exception as e:
        logging.error(f"Error parsing detailed score HTML from {url}: {e}", exc_info=True)
    return None

# --- Worker Threads ---
class HomepageFetcher(QThread):
    matches_updated = pyqtSignal(list)
    fetch_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True

    def run(self):
        while self._running:
            logging.info("Running homepage score update thread.")
            try:
                fetched_matches = fetch_and_parse_cricbuzz()
                if isinstance(fetched_matches, list):
                    self.matches_updated.emit(fetched_matches)
                else:
                    self.fetch_error.emit("Fetch parse error (homepage).")
            except Exception as e:
                 logging.error(f"Exception in homepage fetch thread: {e}", exc_info=True)
                 self.fetch_error.emit(f"Homepage fetch error: {e}")
            # Use QThread.sleep() for interruptible sleep
            count = 0
            while self._running and count < UPDATE_INTERVAL_SECONDS:
                self.sleep(1)
                count += 1
        logging.info("Homepage update thread finished.")

    def stop(self):
         logging.info("Stopping homepage fetcher thread.")
         self._running = False

class DetailedFetcher(QThread):
    score_updated = pyqtSignal(dict)
    fetch_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True
        self._current_url = None
        self._lock = threading.Lock() # Lock for accessing _current_url

    def set_url(self, url):
        with self._lock:
            if url != self._current_url:
                 logging.info(f"DetailedFetcher URL set to: {url}")
                 self._current_url = url
                 # Wake up thread if sleeping
                 self.wake_up()

    def get_url(self):
         with self._lock:
             return self._current_url

    def run(self):
        while self._running:
            url_to_fetch = self.get_url()
            if url_to_fetch:
                logging.debug(f"DetailedFetcher fetching: {url_to_fetch}")
                try:
                    detailed_score_data = fetch_detailed_score(url_to_fetch)
                    # Check if URL changed *while* fetching before emitting
                    if url_to_fetch == self.get_url() and self._running:
                         if detailed_score_data:
                             self.score_updated.emit(detailed_score_data)
                         else:
                              logging.warning(f"No detailed score data returned for {url_to_fetch}")
                              # Emit error or old data? self.fetch_error.emit("Detailed fetch failed")
                except Exception as e:
                    logging.error(f"Exception in detailed fetch thread: {e}", exc_info=True)
                    if url_to_fetch == self.get_url() and self._running:
                        self.fetch_error.emit(f"Detailed fetch error: {e}")
                sleep_interval = DETAILED_UPDATE_INTERVAL_SECONDS
            else:
                sleep_interval = UPDATE_INTERVAL_SECONDS # Sleep longer if no URL

            # Interruptible sleep
            count = 0
            while self._running and count < sleep_interval:
                self.sleep(1)
                # Break sleep early if URL changed
                if url_to_fetch != self.get_url():
                    break
                count += 1

        logging.info("Detailed score update thread finished.")

    def stop(self):
         logging.info("Stopping detailed fetcher thread.")
         self._running = False
         self.wake_up()

    def wake_up(self):
        # QThread doesn't have a direct wake_up like QWaitCondition
        # If it's sleeping, interrupting the sleep is tricky.
        # The loop structure checks the URL frequently, which is often sufficient.
        # For immediate wake-up, advanced signaling (QWaitCondition) or
        # restructuring the sleep might be needed, but adds complexity.
        pass

# --- PyQt UI Classes ---

class ScoreFlyoutWidget(QWidget):
    """The content widget for the flyout."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.vBoxLayout = QVBoxLayout(self)
        self.setWindowFlags(Qt.WindowStaysOnTopHint)  # Always on top
        
        # Create a more modern semi-transparent background with gradient
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(25, 26, 30, 0.92);
                border-radius: 12px;
                border: 1px solid rgba(120, 120, 180, 0.2);
            }
            BodyLabel {
                color: #FFFFFF;
            }
            CaptionLabel {
                color: #AAC8FF;
                font-weight: bold;
            }
        """)

        # Title and main score
        self.titleLabel = BodyLabel("No match selected", self)
        self.scoreLabel = BodyLabel("-", self)
        
        # Detailed stats section
        self.statsContainer = QWidget(self)
        self.statsLayout = QVBoxLayout(self.statsContainer)
        
        # Batting section
        self.battingHeader = CaptionLabel("Batter", self)
        self.battingTable = QWidget(self)
        self.battingLayout = QVBoxLayout(self.battingTable)
        self.battingLayout.setSpacing(2)
        self.battingLayout.setContentsMargins(0, 0, 0, 0)
        
        # Bowling section
        self.bowlingHeader = CaptionLabel("Bowler", self)
        self.bowlingTable = QWidget(self)
        self.bowlingLayout = QVBoxLayout(self.bowlingTable)
        self.bowlingLayout.setSpacing(2)
        self.bowlingLayout.setContentsMargins(0, 0, 0, 0)
        
        # Match info section
        self.infoContainer = QWidget(self)
        self.infoLayout = QVBoxLayout(self.infoContainer)
        self.infoLayout.setSpacing(2)
        self.infoLayout.setContentsMargins(0, 0, 0, 0)
        
        self.partnershipLabel = BodyLabel("", self)
        self.lastWicketLabel = BodyLabel("", self)
        self.lastOversLabel = BodyLabel("", self)
        self.tossLabel = BodyLabel("", self)
        
        self.infoLayout.addWidget(self.partnershipLabel)
        self.infoLayout.addWidget(self.lastWicketLabel)
        self.infoLayout.addWidget(self.lastOversLabel)
        self.infoLayout.addWidget(self.tossLabel)

        # Font settings
        titleFont = QFont()
        titleFont.setPointSize(11)
        titleFont.setBold(True)
        self.titleLabel.setFont(titleFont)

        scoreFont = QFont()
        scoreFont.setPointSize(14)
        scoreFont.setBold(True)
        self.scoreLabel.setFont(scoreFont)
        
        headerFont = QFont()
        headerFont.setPointSize(10)
        headerFont.setBold(True)
        self.battingHeader.setFont(headerFont)
        self.bowlingHeader.setFont(headerFont)

        # Add batting header and table
        self.statsLayout.addWidget(self.battingHeader)
        self.statsLayout.addWidget(self.battingTable)
        
        # Add bowling header and table
        self.statsLayout.addWidget(self.bowlingHeader)
        self.statsLayout.addWidget(self.bowlingTable)
        
        # Add the information section
        self.statsLayout.addWidget(self.infoContainer)

        # Layout adjustments
        self.vBoxLayout.setContentsMargins(15, 12, 15, 12)
        self.vBoxLayout.setSpacing(8)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.scoreLabel)
        self.vBoxLayout.addWidget(self.statsContainer)

        # Appearance
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.titleLabel.setWordWrap(True)
        self.scoreLabel.setAlignment(Qt.AlignCenter)
        self.scoreLabel.setWordWrap(True)
        self.setFixedWidth(FLYOUT_WIDTH)
        self.setObjectName("ScoreFlyoutWidget")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)
        logging.info("Enhanced ScoreFlyoutWidget initialized.")
        
        # Initialize with empty data
        self._clear_tables()

    def _clear_tables(self):
        """Clear all the table widgets to prepare for new data."""
        # Clear batting
        self._clear_layout(self.battingLayout)
        # Clear bowling
        self._clear_layout(self.bowlingLayout)
        
    def _clear_layout(self, layout):
        """Utility function to clear a layout of all widgets."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

    def _create_batter_row(self, batter_name, runs, balls, fours, sixes, sr):
        """Create a row widget for a batter."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)
        
        # Create labels with better styling
        nameLabel = BodyLabel(batter_name, row)
        runsLabel = BodyLabel(runs, row)
        ballsLabel = BodyLabel(balls, row)
        foursLabel = BodyLabel(fours, row)
        sixesLabel = BodyLabel(sixes, row)
        srLabel = BodyLabel(sr, row)
        
        # Set fixed widths for stats columns and better styling
        nameLabel.setMinimumWidth(120)
        nameLabel.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-family: Segoe UI, Arial;")
        
        # Customize stats columns - highlight runs in bolder font
        runsLabel.setStyleSheet("color: #FFFFFF; font-weight: bold; font-family: Segoe UI, Arial;")
        
        # Style other stats
        for label, color in zip(
            [ballsLabel, foursLabel, sixesLabel, srLabel], 
            ["rgba(220, 220, 255, 0.85)", "rgba(180, 230, 180, 0.9)", "rgba(230, 180, 180, 0.9)", "rgba(230, 230, 180, 0.9)"]
        ):
            label.setFixedWidth(40)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color: {color}; font-family: Segoe UI, Arial;")
        
        layout.addWidget(nameLabel)
        layout.addWidget(runsLabel)
        layout.addWidget(ballsLabel)
        layout.addWidget(foursLabel)
        layout.addWidget(sixesLabel)
        layout.addWidget(srLabel)
        
        return row
        
    def _create_bowler_row(self, bowler_name, overs, maidens, runs, wickets, economy):
        """Create a row widget for a bowler."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(4, 3, 4, 3)
        layout.setSpacing(2)
        
        # Create labels with better styling
        nameLabel = BodyLabel(bowler_name, row)
        oversLabel = BodyLabel(overs, row)
        maidensLabel = BodyLabel(maidens, row)
        runsLabel = BodyLabel(runs, row)
        wicketsLabel = BodyLabel(wickets, row)
        ecoLabel = BodyLabel(economy, row)
        
        # Set fixed widths for stats columns and better styling
        nameLabel.setMinimumWidth(120)
        nameLabel.setStyleSheet("color: rgba(255, 255, 255, 0.95); font-family: Segoe UI, Arial;")
        
        # Highlight wickets in bold
        wicketsLabel.setStyleSheet("color: #FFFFFF; font-weight: bold; font-family: Segoe UI, Arial;")
        
        # Style other stats with unique colors
        labels_and_colors = [
            (oversLabel, "rgba(200, 220, 255, 0.9)"),
            (maidensLabel, "rgba(220, 230, 180, 0.9)"),
            (runsLabel, "rgba(230, 180, 180, 0.9)"),
            (ecoLabel, "rgba(220, 220, 180, 0.9)")
        ]
        
        for label, color in labels_and_colors:
            label.setFixedWidth(40)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(f"color: {color}; font-family: Segoe UI, Arial;")
        
        layout.addWidget(nameLabel)
        layout.addWidget(oversLabel)
        layout.addWidget(maidensLabel)
        layout.addWidget(runsLabel)
        layout.addWidget(wicketsLabel)
        layout.addWidget(ecoLabel)
        
        return row

    def update_score(self, match_info):
        """Updates the widget with new score data."""
        title = match_info.get('title', 'N/A')
        score = match_info.get('score', '-')
        logging.debug(f"Flyout updating score: Title='{title}', Score='{score}'")
        
        # Format title to be more readable
        self.titleLabel.setText(title)
        # Make score more prominent
        self.scoreLabel.setText(score)
        
        # Make sure styling is applied
        self.titleLabel.setStyleSheet("""
            font-family: Segoe UI, Arial, sans-serif;
            color: white;
            font-size: 11pt;
            padding: 4px;
            background-color: rgba(40, 45, 80, 0.3);
            border-radius: 6px;
        """)
        
        self.scoreLabel.setStyleSheet("""
            font-family: Segoe UI, Arial, sans-serif;
            color: white;
            font-size: 14pt;
            font-weight: bold;
            padding: 5px;
            background-color: rgba(60, 70, 110, 0.35);
            border-radius: 6px;
        """)
        
        # Clear previous data
        self._clear_tables()
        
        # Style section headers
        self.battingHeader.setStyleSheet("""
            color: rgba(170, 200, 255, 0.9);
            font-weight: bold;
            font-size: 10pt;
            padding-bottom: 2px;
            border-bottom: 1px solid rgba(100, 140, 230, 0.3);
        """)
        
        self.bowlingHeader.setStyleSheet("""
            color: rgba(170, 200, 255, 0.9);
            font-weight: bold;
            font-size: 10pt;
            padding-bottom: 2px;
            padding-top: 8px;
            border-bottom: 1px solid rgba(100, 140, 230, 0.3);
        """)
        
        # Add header rows with styled headers
        batting_header = self._create_batter_row("Batter", "R", "B", "4s", "6s", "SR")
        batting_header.setStyleSheet("background-color: rgba(40, 50, 80, 0.4); border-radius: 4px;")
        self.battingLayout.addWidget(batting_header)
        
        bowling_header = self._create_bowler_row("Bowler", "O", "M", "R", "W", "ECO")
        bowling_header.setStyleSheet("background-color: rgba(40, 50, 80, 0.4); border-radius: 4px;")
        self.bowlingLayout.addWidget(bowling_header)
        
        # Add real batsmen data if available
        batsmen = match_info.get('batsmen', [])
        if batsmen:
            for i, batter in enumerate(batsmen):
                batter_row = self._create_batter_row(
                    batter.get('name', ''),
                    batter.get('runs', ''),
                    batter.get('balls', ''),
                    batter.get('fours', ''),
                    batter.get('sixes', ''),
                    batter.get('sr', '')
                )
                # Alternate row styling
                if i % 2 == 0:
                    batter_row.setStyleSheet("background-color: rgba(30, 35, 60, 0.2); border-radius: 4px;")
                else:
                    batter_row.setStyleSheet("background-color: rgba(40, 45, 70, 0.25); border-radius: 4px;")
                self.battingLayout.addWidget(batter_row)
        else:
            # Show placeholder if no batsmen data
            no_data_row = self._create_batter_row("No batting data", "-", "-", "-", "-", "-")
            no_data_row.setStyleSheet("background-color: rgba(30, 35, 60, 0.2); border-radius: 4px;")
            self.battingLayout.addWidget(no_data_row)
            
        # Add real bowlers data if available
        bowlers = match_info.get('bowlers', [])
        if bowlers:
            for i, bowler in enumerate(bowlers):
                bowler_row = self._create_bowler_row(
                    bowler.get('name', ''),
                    bowler.get('overs', ''),
                    bowler.get('maidens', ''),
                    bowler.get('runs', ''),
                    bowler.get('wickets', ''),
                    bowler.get('economy', '')
                )
                # Alternate row styling
                if i % 2 == 0:
                    bowler_row.setStyleSheet("background-color: rgba(30, 35, 60, 0.2); border-radius: 4px;")
                else:
                    bowler_row.setStyleSheet("background-color: rgba(40, 45, 70, 0.25); border-radius: 4px;")
                self.bowlingLayout.addWidget(bowler_row)
        else:
            # Show placeholder if no bowlers data
            no_data_row = self._create_bowler_row("No bowling data", "-", "-", "-", "-", "-")
            no_data_row.setStyleSheet("background-color: rgba(30, 35, 60, 0.2); border-radius: 4px;")
            self.bowlingLayout.addWidget(no_data_row)
        
        # Style info section
        self.infoContainer.setStyleSheet("""
            background-color: rgba(30, 40, 70, 0.2);
            border-radius: 6px;
            padding: 4px;
            margin-top: 6px;
        """)
        
        # Update match information with real data
        self.partnershipLabel.setStyleSheet("color: rgba(200, 210, 255, 0.9); font-size: 9pt;")
        self.lastWicketLabel.setStyleSheet("color: rgba(200, 210, 255, 0.9); font-size: 9pt;")
        self.lastOversLabel.setStyleSheet("color: rgba(200, 210, 255, 0.9); font-size: 9pt;")
        self.tossLabel.setStyleSheet("color: rgba(200, 210, 255, 0.9); font-size: 9pt;")
        
        # Set real data for match info if available
        self.partnershipLabel.setText(match_info.get('partnership', ''))
        self.lastWicketLabel.setText(match_info.get('last_wicket', ''))
        self.lastOversLabel.setText(match_info.get('recent_overs', ''))
        self.tossLabel.setText(match_info.get('toss', ''))
        
        self.adjustSize()
        
        mini_widget = QWidget()
        mini_widget.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        mini_layout = QVBoxLayout(mini_widget)
        
        score_label = BodyLabel(self.scoreLabel.text(), mini_widget)
        score_font = QFont()
        score_font.setPointSize(12)
        score_font.setBold(True)
        score_label.setFont(score_font)
        
        mini_layout.addWidget(score_label)
        mini_widget.setStyleSheet("background-color: #222222; color: white; border-radius: 4px;")
        mini_layout.setContentsMargins(8, 4, 8, 4)
        
        return mini_widget

class MinimizedScoreWidget(QWidget):
    """An ultra-compact always-on-top widget showing just the essential score."""
    
    expandClicked = pyqtSignal()
    closeClicked = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        # Enable translucent background for acrylic effect
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Main layout - even more compact
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(1, 1, 1, 1)
        self.main_layout.setSpacing(0)
        
        # Content container with background
        self.container = QWidget(self)
        self.container.setObjectName("miniContainer")
        self.container_layout = QHBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 5, 6, 5)
        self.container_layout.setSpacing(2)
        
        # Only show the score
        self.score_label = BodyLabel("", self.container)
        self.score_label.setObjectName("miniScore")
        score_font = QFont()
        score_font.setPointSize(10)
        score_font.setBold(True)
        self.score_label.setFont(score_font)
        
        # Control buttons in a more subtle way
        self.buttons_widget = QWidget(self.container)
        self.buttons_widget.setObjectName("buttonContainer")
        self.buttons_widget.setFixedWidth(24)
        self.buttons_layout = QVBoxLayout(self.buttons_widget)
        self.buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.buttons_layout.setSpacing(1)
        
        self.btn_expand = QPushButton("□", self.buttons_widget)
        self.btn_expand.setObjectName("miniButton")
        self.btn_expand.setFixedSize(20, 14)
        self.btn_expand.setCursor(Qt.PointingHandCursor)
        self.btn_expand.clicked.connect(self.expandClicked.emit)
        
        self.btn_close = QPushButton("×", self.buttons_widget)
        self.btn_close.setObjectName("miniButton")
        self.btn_close.setFixedSize(20, 14)
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.closeClicked.emit)
        
        self.buttons_layout.addWidget(self.btn_expand)
        self.buttons_layout.addWidget(self.btn_close)
        
        # Add widgets to layouts
        self.container_layout.addWidget(self.score_label, 1)
        self.container_layout.addWidget(self.buttons_widget, 0)
        self.main_layout.addWidget(self.container)
        
        # Set up styling with acrylic/mica-like effect and gradients
        self.setStyleSheet("""
            /* Main widget fully transparent */
            QWidget {
                background-color: transparent;
            }
            
            /* Container with acrylic effect - semi-transparent with blur */
            #miniContainer {
                background-color: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(28, 30, 45, 0.90), 
                    stop: 1 rgba(25, 28, 40, 0.85)
                );
                border-radius: 8px;
                border: 1px solid rgba(100, 120, 220, 0.22);
            }
            
            /* Score text with glow effect */
            #miniScore {
                color: #FFFFFF;
                font-weight: bold;
                background-color: transparent;
                font-family: Segoe UI, Arial, sans-serif;
                padding: 2px;
            }
            
            /* Button container transparent */
            #buttonContainer {
                background-color: transparent;
            }
            
            /* Buttons styling */
            #miniButton {
                background-color: rgba(30, 30, 40, 0.5);
                border-radius: 3px;
                border: none;
                color: rgba(180, 180, 220, 0.7);
                font-weight: bold;
                font-size: 10px;
                padding: 0px;
            }
            
            #miniButton:hover {
                background-color: rgba(60, 70, 120, 0.6);
                color: #FFFFFF;
            }
        """)
        
        # Make widget draggable
        self.dragging = False
        self.offset = QPoint()
        
    def update_data(self, title, score):
        """Update the widget with just the score data."""
        # Only use the score, no title
        self.score_label.setText(score)
        self.adjustSize()
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.pos()
            
    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            self.move(self.mapToParent(event.pos() - self.offset))
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False

# --- Main Application Class ---
class TrayApplication(QApplication):
    """Main application class managing tray icon and future UI."""
    def __init__(self, args):
        super().__init__(args)
        logging.info("Initializing TrayApplication (Fluent version)...")
        self.setQuitOnLastWindowClosed(False)
        global matches_data_cache
        matches_data_cache = []
        self.selected_match_info = None
        self._flyout_view = None
        self._mini_widget = None
        self.is_minimized_view = False
        
        self.icon = QIcon(ICON_PATH)
        if self.icon.isNull():
            logging.warning(f"Failed to load icon from {ICON_PATH}, using default.")
            self.icon = create_default_icon()
            if self.icon.isNull():
                 logging.error("Failed to create default icon. Exiting.")
                 sys.exit(1)
                 
        self.tray_icon = QSystemTrayIcon(self.icon, self)
        self.tray_icon.setToolTip("Cricket Scores: Initializing...")
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.menu = QMenu()
        self.populate_menu()
        self.tray_icon.setContextMenu(self.menu)

        # --- Dummy Widget for Positioning ---
        # Needs to be persistent so Flyout.make has a valid target/parent
        self._dummy_target_widget = QWidget()

        # --- Setup & Start Threads ---
        self.homepage_fetcher = HomepageFetcher()
        self.homepage_fetcher.matches_updated.connect(self.handle_matches_update)
        self.homepage_fetcher.fetch_error.connect(self.handle_fetch_error)
        self.detailed_fetcher = DetailedFetcher()
        self.detailed_fetcher.score_updated.connect(self.handle_detailed_score_update)
        self.detailed_fetcher.fetch_error.connect(self.handle_fetch_error)
        
        # Create update timer for minimized view
        self.mini_update_timer = QTimer(self)
        self.mini_update_timer.timeout.connect(self.update_mini_widget)
        self.mini_update_timer.setInterval(15000)  # Update every 15 seconds
        
        self.trigger_refresh() # Start initial fetch
        self.tray_icon.show()
        logging.info("TrayApplication initialized and tray icon shown.")

    def populate_menu(self):
        global matches_data_cache
        logging.debug(f"Populating menu. Cache size: {len(matches_data_cache)}")
        self.menu.clear()
        if not matches_data_cache:
            action = self.menu.addAction("Fetching matches...")
            action.setEnabled(False)
            logging.debug("Menu: Added 'Fetching matches...' item.")
        else:
            added_count = 0
            for i, match in enumerate(matches_data_cache):
                if i >= MAX_MATCHES_MENU: break
                display_text = f"{match.get('title', 'N/A')} - {match.get('score', '?')}"
                # Ensure display_text is not excessively long for menu item
                display_text = display_text[:100] + '...' if len(display_text) > 100 else display_text
                action = self.menu.addAction(display_text)
                # Use lambda to capture the specific match info for the slot
                match_copy = match.copy() # Important: Capture a copy for the lambda
                action.triggered.connect(lambda checked=False, m=match_copy: self.select_match(m))
                logging.debug(f"Menu: Added action for '{match.get('title')}'")
                added_count += 1

            if added_count == 0:
                 action = self.menu.addAction("No live matches found")
                 action.setEnabled(False)
                 logging.debug("Menu: Added 'No live matches found' item.")

        self.menu.addSeparator()
        
        # View mode toggle
        toggle_view_action = self.menu.addAction("Minimized View" if not self.is_minimized_view else "Detailed View")
        toggle_view_action.triggered.connect(self.toggle_view_mode)
        
        refresh_action = self.menu.addAction("Refresh List")
        refresh_action.triggered.connect(self.trigger_refresh)
        logging.debug("Menu: Added 'Refresh List' action.")
        self.menu.addSeparator()
        quit_action = self.menu.addAction("Exit")
        quit_action.triggered.connect(self.quit_app)
        logging.debug("Menu: Added 'Exit' action.")

    def on_tray_activated(self, reason):
        """Handles tray icon activation (clicks)."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger: # Left-click
            logging.info("Tray icon left-clicked (Trigger).")
            if self.is_minimized_view and self.selected_match_info:
                if self._mini_widget and self._mini_widget.isVisible():
                    self._mini_widget.hide()
                else:
                    self.show_minimized_view()
            else:
                self.toggle_flyout()
        elif reason == QSystemTrayIcon.ActivationReason.Context: # Right-click
            logging.info("Tray icon right-clicked (Context) - menu shown automatically.")
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Optional: Toggle between minimized and detailed view
            if self.selected_match_info:
                self.toggle_view_mode()
            pass

    def trigger_refresh(self):
         logging.info("Refresh triggered.")
         self.tray_icon.setToolTip("Refreshing...")
         self.menu.clear()
         action = self.menu.addAction("Refreshing...")
         action.setEnabled(False)
         self.menu.addAction("Exit").triggered.connect(self.quit_app)

         # Restart the fetcher thread
         if self.homepage_fetcher and self.homepage_fetcher.isRunning():
             logging.debug("Stopping existing homepage fetcher for refresh...")
             self.homepage_fetcher.stop()
             if not self.homepage_fetcher.wait(1000): # Wait up to 1 sec
                  logging.warning("Homepage fetcher thread did not stop gracefully.")
             else:
                  logging.debug("Homepage fetcher stopped.")

         logging.debug("Creating and starting new homepage fetcher.")
         self.homepage_fetcher = HomepageFetcher() # Create new instance
         self.homepage_fetcher.matches_updated.connect(self.handle_matches_update)
         self.homepage_fetcher.fetch_error.connect(self.handle_fetch_error)
         self.homepage_fetcher.start()

    def quit_app(self):
        """Cleans up and quits the application."""
        logging.info("Quit triggered.")
        self.tray_icon.hide()
        
        # Clean up the minimized widget if it exists
        if self._mini_widget:
            self._mini_widget.close()
            self._mini_widget = None
        self.mini_update_timer.stop()
        
        # Clean up the flyout
        self.hide_flyout()
        
        # Stop threads
        if self.homepage_fetcher and self.homepage_fetcher.isRunning():
            logging.debug("Stopping homepage fetcher on quit...")
            self.homepage_fetcher.stop()
            self.homepage_fetcher.wait(500)
        if self.detailed_fetcher and self.detailed_fetcher.isRunning():
            logging.debug("Stopping detailed fetcher on quit...")
            self.detailed_fetcher.stop()
            self.detailed_fetcher.wait(500)
        logging.info("Quitting QApplication.")
        self.quit()

    # --- Slot Implementations ---
    def handle_matches_update(self, fetched_matches):
        global matches_data_cache
        logging.info(f"Received {len(fetched_matches)} homepage matches.")
        matches_data_cache = fetched_matches
        new_tooltip = format_tooltip_pyqt(matches_data_cache)
        self.tray_icon.setToolTip(new_tooltip)
        self.populate_menu()

    def handle_detailed_score_update(self, score_data):
        logging.info(f"Received detailed score update: {score_data}")
        # Update the cached data with all available fields from score_data
        if self.selected_match_info and score_data:
            # Update all the fields from score_data to selected_match_info
            for key, value in score_data.items():
                self.selected_match_info[key] = value
                
            logging.debug(f"Updated selected_match_info cache with detailed data")
            
            # Update minimized widget if it's visible
            if self.is_minimized_view and self._mini_widget and self._mini_widget.isVisible():
                self.update_mini_widget()
            
            # Update the flyout if it's visible
            if self._flyout_view and self._flyout_view.isVisible():
                self.hide_flyout()  # Close current flyout
                self.show_flyout()  # Show updated flyout
        else:
            logging.warning("Received detailed score but no match is selected.")

    def handle_fetch_error(self, error_message):
        logging.error(f"Fetch error signal received: {error_message}")
        self.tray_icon.showMessage("Fetch Error", error_message, QSystemTrayIcon.Warning, 3000)

    # --- Menu/Action Handlers ---
    def select_match(self, match_info):
        global selected_match_url_cache
        url = match_info.get('url')
        logging.info(f"Match selected via menu: {match_info.get('title')}")
        if url:
            selected_match_url_cache = url
            self.selected_match_info = match_info
            self.detailed_fetcher.set_url(url)
            if not self.detailed_fetcher.isRunning():
                self.detailed_fetcher.start()
                
            # Show the appropriate view based on current mode
            if self.is_minimized_view:
                self.show_minimized_view()
            else:
                self.show_flyout()
        else:
            logging.warning(f"Selected match has no URL: {match_info.get('title')}")
            self.tray_icon.showMessage("Error", "Cannot get details for this match.", QSystemTrayIcon.Warning, 2000)

    # --- Tray Icon / Flyout Activation ---
    def toggle_flyout(self):
        if self._flyout_view and self._flyout_view.isVisible():
            self.hide_flyout()
        else:
            self.show_flyout()

    def show_flyout(self):
        if self._flyout_view and self._flyout_view.isVisible():
            logging.debug("Flyout already visible.")
            return
        if self._flyout_view:
            # Clean up previous view reference
            try:
                self._flyout_view.closed.disconnect()
            except TypeError:
                pass # Ignore if already disconnected
            self._flyout_view = None

        logging.debug("Showing flyout by creating new widget and view.")

        # --- Create NEW flyout content widget --- #
        flyout_content = ScoreFlyoutWidget()

        # --- Update its content --- #
        if self.selected_match_info:
             flyout_content.update_score(self.selected_match_info)
        else:
             flyout_content.update_score({'title': 'No match selected', 'score': '-'})

        # --- Calculate Position --- #
        cursor_pos = QCursor.pos()
        target_widget_for_pos = self._dummy_target_widget
        target_widget_for_pos.move(cursor_pos)

        # --- Create Flyout View with enhanced animation --- #
        self._flyout_view = Flyout.make(
            flyout_content, # Pass the NEW content widget
            target=target_widget_for_pos,
            parent=self._dummy_target_widget, # Parent to dummy to manage lifetime?
            aniType=FlyoutAnimationType.FADE_IN
        )
        
        # Apply modern style with soft shadow and transparency to the flyout
        if self._flyout_view:
            try:
                # Apply mica/acrylic-like effect to the flyout view itself
                self._flyout_view.setStyleSheet("""
                    QWidget {
                        background-color: rgba(25, 26, 30, 0.0); /* Fully transparent container */
                    }
                    FlyoutViewBase {
                        border-radius: 12px;
                        border: 1px solid rgba(90, 130, 200, 0.2);
                    }
                """)
                
                # Add drop shadow effect if possible
                try:
                    shadow = QGraphicsDropShadowEffect(self._flyout_view)
                    shadow.setBlurRadius(20)
                    shadow.setColor(QColor(0, 0, 0, 120))
                    shadow.setOffset(0, 4)
                    self._flyout_view.setGraphicsEffect(shadow)
                except:
                    logging.debug("Could not apply shadow effect - graphics effects may not be available")
            except Exception as e:
                logging.debug(f"Could not apply modern style to flyout view: {e}")

        if self._flyout_view:
            # Make the flyout window stay on top
            try:
                if hasattr(self._flyout_view, 'windowHandle'):
                    self._flyout_view.windowHandle().setFlags(self._flyout_view.windowHandle().flags() | Qt.WindowStaysOnTopHint)
                elif hasattr(self._flyout_view, 'window'):
                    self._flyout_view.window().setWindowFlags(self._flyout_view.window().windowFlags() | Qt.WindowStaysOnTopHint)
            except Exception as e:
                logging.warning(f"Could not set always-on-top for flyout: {e}")
                
            self._flyout_view.closed.connect(self._on_flyout_closed)
            self._flyout_view.show()
            logging.info(f"Flyout shown near cursor at {cursor_pos}")
        else:
             logging.error("Flyout.make returned None.")

    def hide_flyout(self):
        if self._flyout_view and self._flyout_view.isVisible():
            logging.debug("Hiding flyout.")
            # FlyoutViewBase doesn't have hide(), use close()
            self._flyout_view.close()
            # self._flyout_view = None # Set to None in _on_flyout_closed

    def _on_flyout_closed(self):
        logging.debug("Flyout closed signal received.")
        if self._flyout_view:
            self._flyout_view.closed.disconnect() # Disconnect signal
            self._flyout_view = None

    def toggle_view_mode(self):
        """Toggle between minimized and detailed view modes."""
        self.is_minimized_view = not self.is_minimized_view
        logging.info(f"Toggled view mode. Minimized: {self.is_minimized_view}")
        
        # Update the menu
        self.populate_menu()
        
        # If we have a selected match, update the view
        if self.selected_match_info:
            # Hide current view first
            self.hide_flyout()
            if self._mini_widget:
                self._mini_widget.hide()
                self._mini_widget.close()
                self._mini_widget = None
            
            # Show the appropriate view
            if self.is_minimized_view:
                self.show_minimized_view()
            else:
                self.show_flyout()
                
    def show_minimized_view(self):
        """Show the minimized always-on-top score widget."""
        if not self.selected_match_info:
            logging.warning("Cannot show minimized view: No match selected")
            return
            
        # Clean up any existing minimized widget
        if self._mini_widget:
            self._mini_widget.close()
            
        # Create and configure the new minimized widget
        self._mini_widget = MinimizedScoreWidget()
        self._mini_widget.expandClicked.connect(self.on_mini_expand)
        self._mini_widget.closeClicked.connect(self.on_mini_close)
        
        # Update its content with selected match info
        title = self.selected_match_info.get('title', 'No match')
        score = self.selected_match_info.get('score', '-')
        self._mini_widget.update_data(title, score)
        
        # Position it at the cursor location
        cursor_pos = QCursor.pos()
        self._mini_widget.move(cursor_pos.x() - 100, cursor_pos.y() - 20) # Offset slightly
        
        # Show the widget and start the update timer
        self._mini_widget.show()
        self.mini_update_timer.start()
        logging.info(f"Minimized score widget shown at {cursor_pos}")
        
    def update_mini_widget(self):
        """Update the minimized widget with the latest score."""
        if self._mini_widget and self.selected_match_info:
            title = self.selected_match_info.get('title', 'No match')
            score = self.selected_match_info.get('score', '-')
            
            # Format for minimized view: "TEAM 126/2 (12.1) CRR: 10.36"
            # or for limited matches: "TEAM1 126 & 253 | TEAM2 42 & 75/2 (12.1)"
            simplified_score = score
            try:
                # Extract status if present (like "live", "stumps", etc)
                status = ""
                status_pattern = r'\((Live|Stumps|Lunch|Tea|End of Day|Match abandoned|Match called off|Match delayed|Rain|Innings Break|Complete)\)'
                status_match = re.search(status_pattern, score, re.IGNORECASE)
                if status_match:
                    status = status_match.group(1)
                
                # Try to get team names from title
                teams = []
                if " vs " in title:
                    teams = [team.strip() for team in title.split(" vs ")]
                elif " Vs. " in title:
                    teams = [team.strip() for team in title.split(" Vs. ")]
                
                # Get batting team abbreviation
                batting_team = ""
                if teams and len(teams) > 0:
                    # Use abbreviation if possible
                    words = teams[0].split()
                    if len(words) > 1:
                        batting_team = ''.join([word[0] for word in words if word[0].isupper()])
                    else:
                        batting_team = teams[0][:3].upper()
                
                # Extract score components with regex
                score_parts = []
                
                # Look for patterns like "126/2" or "126-2"
                runs_pattern = r'(\d+)[/-](\d+)'
                runs_matches = re.finditer(runs_pattern, score)
                
                # Look for overs pattern "(12.1)"
                overs_pattern = r'\((\d+\.\d+|\d+) overs?\)'
                overs_match = re.search(overs_pattern, score)
                if not overs_match:
                    overs_pattern = r'\((\d+\.\d+|\d+)\)'
                    overs_match = re.search(overs_pattern, score)
                
                # Look for run rate "CRR: 10.36" or "RR: 10.36"
                rr_pattern = r'(?:CRR|RR):\s*(\d+\.\d+)'
                rr_match = re.search(rr_pattern, score)
                
                # If all components found, build the formatted score
                if batting_team and runs_matches:
                    for match in runs_matches:
                        score_parts.append(f"{match.group(0)}")
                    
                    # Get overs if available
                    overs = ""
                    if overs_match:
                        overs = f"({overs_match.group(1)})"
                        score_parts.append(overs)
                    
                    # Get run rate if available
                    rr = ""
                    if rr_match:
                        rr = f"CRR: {rr_match.group(1)}"
                        score_parts.append(rr)
                    
                    # Add status if available (for non-live matches)
                    if status and status.lower() != "live":
                        score_parts.append(status)
                    
                    # Build final score
                    simplified_score = f"{batting_team} {' '.join(score_parts)}"
                else:
                    # Simplified fallback - keep only crucial info
                    # Clean up the score by removing extra text
                    score_clean = re.sub(r'(?i)\(.*?(won|lead|trail|by|batting|bowl|opt|chose).*?\)', '', score)
                    score_clean = re.sub(r'(?i)need \d+ runs.*?$', 'batting', score_clean)
                    simplified_score = score_clean.strip()
                    
                    # Add team prefix if possible
                    if batting_team:
                        simplified_score = f"{batting_team} {simplified_score}"
                
                # Limit the length for display
                simplified_score = simplified_score[:40]
                    
            except Exception as e:
                # If any parsing error, use the original score (but abbreviated)
                logging.debug(f"Could not simplify score, using original: {e}")
                simplified_score = score[:40]
                
            self._mini_widget.update_data(title, simplified_score)
            logging.debug(f"Minimized widget updated: {simplified_score}")
            
    def on_mini_expand(self):
        """Handle expand button click in minimized view."""
        logging.info("Expand button clicked on minimized view")
        self.toggle_view_mode()
        
    def on_mini_close(self):
        """Handle close button click in minimized view."""
        logging.info("Close button clicked on minimized view")
        if self._mini_widget:
            self._mini_widget.close()
            self._mini_widget = None
        self.mini_update_timer.stop()

# --- Main Execution ---
if __name__ == "__main__":
    # Required for font rendering etc.
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = TrayApplication(sys.argv)

    # Set Fluent theme (optional, requires qfluentwidgets)
    try:
        setTheme(Theme.DARK) # Or Theme.LIGHT or Theme.AUTO
        logging.info(f"Applied Fluent theme: {Theme.DARK}")
    except Exception as e:
        logging.warning(f"Could not apply Fluent theme: {e}")

    logging.info("Starting application event loop...")
    sys.exit(app.exec_()) 
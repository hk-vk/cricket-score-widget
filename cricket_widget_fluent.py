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
FLYOUT_WIDTH = 300 # Reduced from 320
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

        result = {'title': 'N/A', 'score': 'N/A', 'batters': [], 'bowlers': []}

        # Extract title
        title_tag = soup.select_one('h1.cb-nav-hdr, div.cb-nav-main h1')
        if title_tag:
            result['title'] = title_tag.get_text(strip=True)[:150]
        else: # Fallback using <title> tag
            html_title = soup.find('title')
            if html_title:
                result['title'] = html_title.text.split('|')[0].strip()[:150]


        # Extract main score line and status
        score_line = ""
        score_div = soup.select_one('div.cb-min-bat-rw') # Main score line container
        if score_div:
            score_span = score_div.select_one('span.cb-font-20') # Actual score part
            if score_span:
                score_line = score_span.get_text(strip=True)

        status_tag = soup.select_one('div.cb-text-inprogress, div.cb-text-complete, div.cb-text-stump, div.cb-text-lunch, div.cb-text-tea, div.cb-text-preview') # Match status
        status_text = ""
        if status_tag:
            status_text = status_tag.get_text(strip=True)

        result['score'] = f"{score_line} ({status_text})" if status_text else score_line
        result['score'] = result['score'][:150] # Limit length


        # Find the batting and bowling sections specifically
        all_min_inf_divs = soup.select("div.cb-min-inf")
        batting_section = None
        bowling_section = None

        for section in all_min_inf_divs:
            header = section.select_one("div.cb-min-hdr-rw")
            if header:
                header_text = header.get_text().lower()
                if "batter" in header_text:
                    batting_section = section
                elif "bowler" in header_text:
                    bowling_section = section

        # Extract current batters from the identified batting section
        if batting_section:
            batter_rows = batting_section.select('div.cb-min-itm-rw')
            for row in batter_rows:
                cols = row.select('div.cb-col')
                if len(cols) >= 6: # Ensure we have all columns
                    name_col = cols[0].select_one('a.cb-text-link')
                    if name_col:
                        # Check if the first column contains a link (likely a player name)
                        batter = {
                            'name': name_col.get_text(strip=True) + (" *" if "*" in cols[0].get_text() else ""), # Add asterisk if present
                            'runs': cols[1].get_text(strip=True),
                            'balls': cols[2].get_text(strip=True),
                            'fours': cols[3].get_text(strip=True),
                            'sixes': cols[4].get_text(strip=True),
                            'sr': cols[5].get_text(strip=True)
                        }
                        result['batters'].append(batter)

        # Extract current bowlers from the identified bowling section
        if bowling_section:
            bowler_rows = bowling_section.select('div.cb-min-itm-rw')
            for row in bowler_rows:
                cols = row.select('div.cb-col')
                if len(cols) >= 6: # Ensure we have all columns
                    name_col = cols[0].select_one('a.cb-text-link')
                    if name_col:
                         # Check if the first column contains a link (likely a player name)
                        bowler = {
                            'name': name_col.get_text(strip=True) + (" *" if "*" in cols[0].get_text() else ""), # Add asterisk if present
                            'overs': cols[1].get_text(strip=True),
                            'maidens': cols[2].get_text(strip=True),
                            'runs': cols[3].get_text(strip=True),
                            'wickets': cols[4].get_text(strip=True),
                            'economy': cols[5].get_text(strip=True)
                        }
                        result['bowlers'].append(bowler)

        logging.info(f"Detailed score parsed: Title='{result['title']}', Score='{result['score']}', Batters: {len(result['batters'])}, Bowlers: {len(result['bowlers'])}")
        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching detailed score: {e}")
    except Exception as e:
        logging.error(f"Error parsing detailed score HTML: {e}", exc_info=True)
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
        # Removed setWindowFlags - already handled by Flyout.make

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("""
            QWidget {
                background-color: rgba(25, 26, 30, 0.92); /* Slightly darker background */
                border-radius: 8px; /* Slightly smaller radius */
                border: 1px solid rgba(120, 120, 180, 0.15); /* More subtle border */
                padding: 8px; /* Add padding to main widget */
            }
            BodyLabel {
                color: #E0E0E0; /* Slightly less bright white */
                background-color: transparent; /* Ensure labels have transparent background */
            }
            CaptionLabel {
                color: #A0B8FF; /* Slightly adjusted caption color */
                font-weight: bold;
                background-color: transparent;
                padding-bottom: 2px; /* Spacing for headers */
            }
        """)

        # Title and score section
        self.titleLabel = BodyLabel("", self)
        self.scoreLabel = BodyLabel("", self)

        # Corrected stylesheet definition with standard triple quotes
        self.titleLabel.setStyleSheet("""
            font-family: Segoe UI, Arial, sans-serif;
            color: #D0D0FF;
            font-size: 10pt; /* Reduced from 11pt */
            padding: 4px;
            background-color: transparent;
            border: none;
            text-align: center;
        """)
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.titleLabel.setWordWrap(True)

        # Corrected stylesheet definition with standard triple quotes
        self.scoreLabel.setStyleSheet("""
            font-family: Segoe UI, Arial, sans-serif;
            color: white;
            font-size: 12pt; /* Further reduced from 14pt */
            font-weight: bold;
            padding: 4px; /* Adjusted padding */
            background-color: rgba(50, 55, 90, 0.4);
            border-radius: 4px; /* Adjusted radius */
            border: none;
            text-align: center;
            margin-bottom: 5px; /* Add margin below score */
        """)
        self.scoreLabel.setAlignment(Qt.AlignCenter)
        self.scoreLabel.setWordWrap(True)


        # Batting section (Table only, header added in update_score)
        # self.battingHeader = CaptionLabel("Batting", self) # REMOVED
        self.battingTable = QWidget(self)
        self.battingLayout = QVBoxLayout(self.battingTable)
        self.battingLayout.setSpacing(4) # Increased spacing slightly
        self.battingLayout.setContentsMargins(0, 2, 0, 5) # Adjusted margins


        # Bowling section (Table only, header added in update_score)
        # self.bowlingHeader = CaptionLabel("Bowling", self) # REMOVED
        self.bowlingTable = QWidget(self)
        self.bowlingLayout = QVBoxLayout(self.bowlingTable)
        self.bowlingLayout.setSpacing(4) # Increased spacing slightly
        self.bowlingLayout.setContentsMargins(0, 2, 0, 5) # Adjusted margins


        # Add sections to main layout - WITHOUT the separate headers
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.scoreLabel)
        self.vBoxLayout.addSpacing(8) # Adjusted spacing
        # self.vBoxLayout.addWidget(self.battingHeader) # REMOVED
        self.vBoxLayout.addWidget(self.battingTable)
        self.vBoxLayout.addSpacing(8) # Adjusted spacing
        # self.vBoxLayout.addWidget(self.bowlingHeader) # REMOVED
        self.vBoxLayout.addWidget(self.bowlingTable)
        self.vBoxLayout.addStretch(1) # Add stretch to push content up

        # --- Font settings are now handled via Stylesheets ---

        # --- Shadow effect can be applied to the FlyoutView itself for better performance ---
        # Removed shadow effect from here

        # Set overall widget properties
        self.setFixedWidth(FLYOUT_WIDTH)
        self.setObjectName("ScoreFlyoutWidget")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding) # Allow vertical expansion

        logging.info("ScoreFlyoutWidget initialized (UI Refined).")
        self._clear_tables() # Clear tables on init

    def _abbreviate_name(self, full_name):
        """Abbreviates a full name like 'First Last *' to 'F. Last *'. Strips trailing numbers."""
        if not full_name or not isinstance(full_name, str):
            return ""

        # Handle potential asterisk indicating 'not out' or current bowler
        asterisk = " *" if "*" in full_name else ""
        name_part = full_name.replace("*", "").strip()
        
        # Remove potential trailing numbers/stats (like runs/balls) sometimes included in name field
        name_part = re.sub(r'\s+\d+.*$', '', name_part).strip()
        
        parts = name_part.split()
        
        if len(parts) > 1:
            # Take first initial of the first name, and the full last name
            initial = parts[0][0].upper() + "."
            # Handle multi-part last names if necessary, though joining remaining parts is safer
            last_name = " ".join(p.capitalize() for p in parts[1:]) 
            return f"{initial} {last_name}{asterisk}"
        elif len(parts) == 1:
            # If only one name part, return it capitalized
            return parts[0].capitalize() + asterisk
        else:
            return "" # Return empty string if name is empty after processing

    def _clear_tables(self):
        self._clear_layout(self.battingLayout)
        self._clear_layout(self.bowlingLayout)
        
    def _clear_layout(self, layout):
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()
                else:
                    self._clear_layout(item.layout())
                    
    def _create_batter_row(self, batter_name, runs, balls, fours, sixes, sr):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2) # Slightly more horizontal margin
        row_layout.setSpacing(5) # Slightly more spacing

        # Create labels
        abbreviated_name = self._abbreviate_name(batter_name)
        name_label = BodyLabel(abbreviated_name)
        runs_label = BodyLabel(str(runs))
        balls_label = BodyLabel(str(balls))
        fours_label = BodyLabel(str(fours))
        sixes_label = BodyLabel(str(sixes))
        sr_label = BodyLabel(str(sr))

        # Styling and Alignment
        name_label.setMinimumWidth(110) # Ensure enough space for name
        name_label.setWordWrap(False) # Prevent wrapping for short names
        name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # Set fixed widths and center alignment for stat columns
        stat_width = 35
        runs_label.setFixedWidth(stat_width)
        runs_label.setAlignment(Qt.AlignCenter)
        runs_label.setStyleSheet("font-weight: bold;") 
        
        balls_label.setFixedWidth(stat_width)
        balls_label.setAlignment(Qt.AlignCenter)
        
        fours_label.setFixedWidth(stat_width)
        fours_label.setAlignment(Qt.AlignCenter)
        
        sixes_label.setFixedWidth(stat_width)
        sixes_label.setAlignment(Qt.AlignCenter)
        
        sr_label.setFixedWidth(45) # Slightly wider for SR
        sr_label.setAlignment(Qt.AlignCenter)
        sr_label.setStyleSheet("color: #C0C0F0;")

        # Add widgets to layout (No stretch factors needed with fixed widths)
        row_layout.addWidget(name_label)
        row_layout.addStretch(1) # Add stretch after name
        row_layout.addWidget(runs_label)
        row_layout.addWidget(balls_label)
        row_layout.addWidget(fours_label)
        row_layout.addWidget(sixes_label)
        row_layout.addWidget(sr_label)

        return row_widget # Return the widget containing the layout

    def _create_bowler_row(self, bowler_name, overs, maidens, runs, wickets, economy):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(4, 2, 4, 2) 
        row_layout.setSpacing(5) 

        # Create labels
        abbreviated_name = self._abbreviate_name(bowler_name)
        name_label = BodyLabel(abbreviated_name)
        overs_label = BodyLabel(str(overs))
        maidens_label = BodyLabel(str(maidens))
        runs_label = BodyLabel(str(runs))
        wickets_label = BodyLabel(str(wickets))
        economy_label = BodyLabel(str(economy))

        # Styling and Alignment
        name_label.setMinimumWidth(110) 
        name_label.setWordWrap(False) 
        name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        # Set fixed widths and center alignment for stat columns
        stat_width = 35
        overs_label.setFixedWidth(stat_width)
        overs_label.setAlignment(Qt.AlignCenter)
        
        maidens_label.setFixedWidth(stat_width)
        maidens_label.setAlignment(Qt.AlignCenter)
        
        runs_label.setFixedWidth(stat_width)
        runs_label.setAlignment(Qt.AlignCenter)
        
        wickets_label.setFixedWidth(stat_width)
        wickets_label.setAlignment(Qt.AlignCenter)
        wickets_label.setStyleSheet("font-weight: bold;") 
        
        economy_label.setFixedWidth(45) # Slightly wider for ECO
        economy_label.setAlignment(Qt.AlignCenter)
        economy_label.setStyleSheet("color: #C0C0F0;") 

        # Add widgets to layout
        row_layout.addWidget(name_label)
        row_layout.addStretch(1) # Add stretch after name
        row_layout.addWidget(overs_label)
        row_layout.addWidget(maidens_label)
        row_layout.addWidget(runs_label)
        row_layout.addWidget(wickets_label)
        row_layout.addWidget(economy_label)

        return row_widget # Return the widget containing the layout

    def update_score(self, match_info):
        if not match_info:
            # Optionally set default text or hide sections
            self.titleLabel.setText("No match selected")
            self.scoreLabel.setText("-")
            self._clear_tables()
            # Add placeholder rows if desired
            self._add_placeholder_row(self.battingLayout, self._create_batter_row("No batting data", "-", "-", "-", "-", "-"))
            self._add_placeholder_row(self.bowlingLayout, self._create_bowler_row("No bowling data", "-", "-", "-", "-", "-"))
            return

        title = match_info.get('title', 'N/A')
        score = match_info.get('score', 'N/A')

        self.titleLabel.setText(title)
        self.scoreLabel.setText(score)

        # Clear existing tables before adding new data
        self._clear_tables()

        # Add Batting Data
        self._add_section_header(self.battingLayout, "Batter", "R", "B", "4s", "6s", "SR")
        batsmen = match_info.get('batters', [])
        if batsmen:
            for i, batter in enumerate(batsmen):
                row_widget = self._create_batter_row(
                    batter.get('name', ''),
                    batter.get('runs', ''),
                    batter.get('balls', ''),
                    batter.get('fours', ''),
                    batter.get('sixes', ''),
                    batter.get('sr', '')
                )
                # Alternate row background (subtle)
                if i % 2 == 0:
                     row_widget.setStyleSheet("background-color: rgba(255, 255, 255, 0.02); border-radius: 3px;")
                self.battingLayout.addWidget(row_widget)
        else:
            self._add_placeholder_row(self.battingLayout, self._create_batter_row("No batting data", "-", "-", "-", "-", "-"))


        # Add Bowling Data
        self._add_section_header(self.bowlingLayout, "Bowler", "O", "M", "R", "W", "ECO")
        bowlers = match_info.get('bowlers', [])
        if bowlers:
            for i, bowler in enumerate(bowlers):
                row_widget = self._create_bowler_row(
                    bowler.get('name', ''),
                    bowler.get('overs', ''),
                    bowler.get('maidens', ''),
                    bowler.get('runs', ''),
                    bowler.get('wickets', ''),
                    bowler.get('economy', '')
                )
                # Alternate row background (subtle)
                if i % 2 == 0:
                    row_widget.setStyleSheet("background-color: rgba(255, 255, 255, 0.02); border-radius: 3px;")
                self.bowlingLayout.addWidget(row_widget)
        else:
             self._add_placeholder_row(self.bowlingLayout, self._create_bowler_row("No bowling data", "-", "-", "-", "-", "-"))


        # Adjust size after updates - Important for dynamic content
        self.adjustSize()
        
    def _add_section_header(self, layout, *headers):
        """Adds a styled header row to a given layout."""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(4, 2, 4, 2) # Match data row margins
        header_layout.setSpacing(5) # Match data row spacing

        # Headers corresponding to columns: Name, R, B, 4s, 6s, SR or Name, O, M, R, W, ECO
        col_headers = headers 
        stat_width = 35 # Must match data rows
        last_col_width = 45 # Must match data rows

        # Name Header
        name_label = CaptionLabel(col_headers[0])
        name_label.setMinimumWidth(110) # Match data rows
        name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header_layout.addWidget(name_label)
        header_layout.addStretch(1) # Match data rows

        # Stat Headers (R/B/4s/6s or O/M/R/W)
        for header_text in col_headers[1:-1]:
            label = CaptionLabel(header_text)
            label.setFixedWidth(stat_width)
            label.setAlignment(Qt.AlignCenter)
            header_layout.addWidget(label)

        # Last Header (SR or ECO)
        last_label = CaptionLabel(col_headers[-1])
        last_label.setFixedWidth(last_col_width)
        last_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(last_label)
        
        header_widget.setStyleSheet("""background-color: rgba(80, 90, 130, 0.2);
                                      border-bottom: 1px solid rgba(120, 120, 180, 0.1);
                                      border-radius: 3px;
                                      margin-bottom: 2px;""")
        layout.addWidget(header_widget)
        
    def _add_placeholder_row(self, layout, row_widget):
         """Adds a placeholder row with specific styling."""
         # Corrected stylesheet definition with standard triple quotes
         row_widget.setStyleSheet("""background-color: rgba(255, 255, 255, 0.02);
                                    border-radius: 3px;
                                    font-style: italic;
                                    color: #AAAAAA;""")
         layout.addWidget(row_widget)

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
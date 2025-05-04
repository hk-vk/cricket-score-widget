# cricket_widget_fluent.py

# --- Imports ---
import sys
import time
import threading
import logging
import requests
import re
import traceback
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

        # Initialize with defaults
        result = {'title': 'N/A', 'score': 'N/A', 'opponent_score': None, 
                  'status': '', 'batters': [], 'bowlers': [], 
                  'team1_name': None, 'team2_name': None, 'pom': None, # Player of the Match
                  'is_complete': False} 

        # Extract title and team names (as before)
        title_text = 'N/A'
        title_tag = soup.select_one('h1.cb-nav-hdr, div.cb-nav-main h1')
        if title_tag:
            title_text = title_tag.get_text(strip=True)[:150]
        else: # Fallback using <title> tag
            html_title = soup.find('title')
            if html_title:
                title_text = html_title.text.split('|')[0].strip()[:150]
        result['title'] = title_text

        # --- Attempt to parse team names from title ---
        vs_match = re.search(r'^(.*?) vs (.*?),(.*)', title_text)
        if vs_match:
            result['team1_name'] = vs_match.group(1).strip()
            result['team2_name'] = vs_match.group(2).strip()
            logging.info(f"Parsed teams from title: {result['team1_name']} vs {result['team2_name']}")

        # --- Score and Status Extraction (Handles Live and Completed) ---
        score_wrapper = soup.select_one('div.cb-scrs-wrp')
        status_element = soup.select_one('div.cb-min-stts')

        if score_wrapper:
            team_scores = score_wrapper.select('div.cb-min-tm')
            if len(team_scores) == 2:
                # Likely a completed or between-innings state
                result['is_complete'] = True # Assume complete if two scores shown
                score1 = team_scores[0].get_text(strip=True)
                score2 = team_scores[1].get_text(strip=True)
                # Assign based on which team name appears first in score (crude check)
                if result['team1_name'] and result['team1_name'] in score1:
                    result['score'] = score1
                    result['opponent_score'] = score2
                elif result['team1_name'] and result['team1_name'] in score2: # Check if team1 is second score
                     result['score'] = score2
                     result['opponent_score'] = score1
                else: # Fallback if team names didn't parse or match
                    result['score'] = score1 # Assign arbitrarily
                    result['opponent_score'] = score2
                logging.info(f"Completed scores found: {result['score']} | {result['opponent_score']}")
                
                # Check if it's ACTUALLY complete based on status
                if status_element:
                     status_text = status_element.get_text(strip=True)
                     result['status'] = status_text
                     if "won by" in status_text.lower() or "draw" in status_text.lower() or "tied" in status_text.lower() or "no result" in status_text.lower():
                         result['is_complete'] = True
                         logging.info(f"Match confirmed complete. Status: {status_text}")
                     else:
                         # Might be between innings, not strictly complete yet for final details
                         result['is_complete'] = False 
                         logging.info(f"Two scores, but status suggests not fully complete: {status_text}")


            elif len(team_scores) == 1:
                 # Likely a live match, one team batting
                 result['is_complete'] = False
                 batting_score_raw = team_scores[0].get_text(strip=True)
                 # Try to find opponent score in the grey text above
                 opponent_score_tag = score_wrapper.select_one('div.cb-text-gray')
                 if opponent_score_tag:
                     result['opponent_score'] = opponent_score_tag.get_text(strip=True)
                 
                 # Assign batting score - crude check based on team names if available
                 if result['team1_name'] and result['team1_name'] in batting_score_raw:
                     result['score'] = batting_score_raw
                 elif result['team2_name'] and result['team2_name'] in batting_score_raw:
                      # Batting score is team2, so opponent_score might be team1's if available
                      result['score'] = batting_score_raw 
                 else: # Fallback
                     result['score'] = batting_score_raw

                 logging.info(f"Live score found: {result['score']}")
                 if result['opponent_score']:
                     logging.info(f"Opponent score found: {result['opponent_score']}")

        # Extract Status (if not already found for completed match)
        if not result['status'] and status_element:
            result['status'] = status_element.get_text(strip=True)
            logging.info(f"Match status found: {result['status']}")
            if "won by" in result['status'].lower() or "draw" in result['status'].lower() or "tied" in result['status'].lower() or "no result" in result['status'].lower():
                 result['is_complete'] = True # Update completion status if status indicates end


        # --- Player of the Match (POM) Extraction ---
        if result['is_complete']:
             pom_item = soup.select_one('div.cb-mom-itm')
             if pom_item:
                 pom_label = pom_item.select_one('span.cb-text-gray')
                 pom_name_tag = pom_item.select_one('a.cb-link-undrln')
                 if pom_label and "PLAYER OF THE MATCH" in pom_label.get_text(strip=True) and pom_name_tag:
                     pom_name = pom_name_tag.get_text(strip=True)
                     result['pom'] = pom_name
                     logging.info(f"Player of the Match found: {pom_name}")


        # --- Batter and Bowler Extraction (Remains the same) ---
        # Find the main container for batting and bowling tables
        # ... (rest of batter/bowler extraction logic) ...
        
        logging.debug(f"Final parsed result: {result}")
        return result

    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching detailed score from {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error parsing detailed score from {url}: {e}")
        traceback.print_exc() # Print full traceback for parsing errors
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
    """The content widget for the flyout (now acting as a draggable widget)."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        # --- Window Setup ---
        # Make borderless, tool window (less taskbar presence), initially on top
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._is_pinned = True # Start pinned (Always on Top)
        self.dragging = False
        self.offset = QPoint()
        
        # --- Main Layout ---
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0) # No margins for the main container
        self.mainLayout.setSpacing(0)
        
        # --- Content Container (for background/border) ---
        self.containerWidget = QWidget(self)
        self.containerWidget.setObjectName("ContainerWidget") # For specific styling
        self.vBoxLayout = QVBoxLayout(self.containerWidget) # Layout *inside* the container
        self.vBoxLayout.setContentsMargins(8, 5, 8, 8) # Inner padding
        self.vBoxLayout.setSpacing(5)
        self.mainLayout.addWidget(self.containerWidget)
        
        # Apply base styling to the container
        self.containerWidget.setStyleSheet("""
            #ContainerWidget {
                background-color: rgba(25, 26, 30, 0.92);
                border-radius: 8px;
                border: 1px solid rgba(120, 120, 180, 0.15);
            }
            BodyLabel {
                color: #E0E0E0;
                background-color: transparent;
            }
            CaptionLabel {
                color: #A0B8FF;
                font-weight: bold;
                background-color: transparent;
                padding-bottom: 2px;
            }
            QPushButton#PinButton {
                background-color: transparent;
                border: none;
                color: #A0B8FF;
                font-size: 12pt;
                padding: 0px 2px;
                max-width: 20px;
                max-height: 20px;
            }
            QPushButton#PinButton:hover {
                color: #FFFFFF;
            }
        """)

        # --- Top Bar (for Pin Button) ---
        self.topBarLayout = QHBoxLayout()
        self.topBarLayout.setContentsMargins(0, 0, 0, 0)
        self.topBarLayout.addStretch(1)
        # Start pinned, so button shows the 'unpin' action initially
        self.pinButton = QPushButton('➖', self.containerWidget) # UNPINNED icon initially
        self.pinButton.setObjectName("PinButton")
        self.pinButton.setToolTip("Toggle Always on Top (Unpinned)") # Tooltip reflects unpin action
        self.pinButton.setCursor(Qt.PointingHandCursor)
        self.pinButton.setFocusPolicy(Qt.NoFocus) # Prevent focus rectangle
        self.pinButton.clicked.connect(self.toggle_pinned_state)
        self.topBarLayout.addWidget(self.pinButton)
        self.vBoxLayout.addLayout(self.topBarLayout) # Add top bar to container layout

        # --- Score and Status Labels ---
        self.scoreLabel = BodyLabel("", self.containerWidget)
        self.statusLabel = BodyLabel("", self.containerWidget)
        
        # Styling for score and status
        self.scoreLabel.setStyleSheet("""
            font-family: Segoe UI, Arial, sans-serif;
            color: white;
            font-size: 12pt;
            font-weight: bold;
            padding: 4px;
            background-color: rgba(50, 55, 90, 0.4);
            border-radius: 4px;
            border: none;
            text-align: center;
            margin-bottom: 0px; /* Remove margin, use status label margin */
        """)
        self.scoreLabel.setAlignment(Qt.AlignCenter)
        self.scoreLabel.setWordWrap(True)

        self.statusLabel.setStyleSheet("""
            font-family: Segoe UI, Arial, sans-serif;
            color: #E8E8E8;
            font-size: 10pt;
            font-weight: normal;
            background-color: rgba(45, 50, 80, 0.35);
            border-radius: 4px;
            border: none;
            text-align: center;
            padding: 3px;
            margin-top: 2px;
            margin-bottom: 8px; /* Increased bottom margin */
        """)
        self.statusLabel.setAlignment(Qt.AlignCenter)
        self.statusLabel.setWordWrap(True)

        # Add score/status to container layout
        self.vBoxLayout.addWidget(self.scoreLabel)
        self.vBoxLayout.addWidget(self.statusLabel)

        # --- Batting Section ---
        self.battingTable = QWidget(self.containerWidget)
        self.battingLayout = QVBoxLayout(self.battingTable)
        self.battingLayout.setSpacing(4)
        self.battingLayout.setContentsMargins(0, 2, 0, 5)

        # --- Bowling Section ---
        self.bowlingTable = QWidget(self.containerWidget)
        self.bowlingLayout = QVBoxLayout(self.bowlingTable)
        self.bowlingLayout.setSpacing(4)
        self.bowlingLayout.setContentsMargins(0, 2, 0, 5)

        # Add Tables to container layout
        self.vBoxLayout.addWidget(self.battingTable)
        self.vBoxLayout.addSpacing(5) # Spacing between tables
        self.vBoxLayout.addWidget(self.bowlingTable)
        self.vBoxLayout.addStretch(1)

        # Set overall widget properties
        self.setFixedWidth(FLYOUT_WIDTH)
        self.setObjectName("ScoreDetailedWidget") # Changed name
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

        logging.info("ScoreDetailedWidget initialized.")
        self._clear_tables()

    def toggle_pinned_state(self):
        """Toggles the always-on-top state reliably."""
        self._is_pinned = not self._is_pinned

        # Store state *before* changing flags/visibility
        current_pos = self.pos()
        is_visible = self.isVisible()

        # Determine new flags and button state based on the *new* pinned status
        if self._is_pinned:
            # We just pinned it
            new_flags = self.windowFlags() | Qt.WindowStaysOnTopHint
            self.pinButton.setText('➖') # Pinned icon
            self.pinButton.setToolTip("Toggle Always on Top (Pinned)")
            logging.debug("Widget pinned (Always on Top enabled)")
        else:
            # We just unpinned it
            new_flags = self.windowFlags() & ~Qt.WindowStaysOnTopHint
            self.pinButton.setText('📌') # Unpinned icon
            self.pinButton.setToolTip("Toggle Always on Top (Unpinned)")
            logging.debug("Widget unpinned (Always on Top disabled)")

        # Try hide -> setFlags -> move -> show sequence for robustness
        if is_visible:
            self.hide()

        self.setWindowFlags(new_flags)
        self.move(current_pos) # Ensure position is maintained

        if is_visible:
            self.show()
            self.activateWindow() # Try to bring it forward

    # --- Event Handlers ---
    def focusOutEvent(self, event):
        """Hides the widget if it loses focus *and* is not pinned."""
        # Check if the widget is losing focus to something outside itself
        # and most importantly, only hide if it's *not* pinned.
        if not self._is_pinned and self.isVisible() and QApplication.focusWidget() != self:
            # Check if the new focus widget is a child of this widget
            # to prevent hiding when interacting with internal elements (like the pin button itself)
            new_focus_widget = QApplication.focusWidget()
            is_child = False
            if new_focus_widget:
                parent = new_focus_widget.parent()
                while parent:
                    if parent == self:
                        is_child = True
                        break
                    parent = parent.parent()

            if not is_child:
                logging.debug("Hiding unpinned widget due to focus loss.")
                self.hide()
            else:
                logging.debug("Focus moved to a child widget, not hiding.")

        # Call the base class implementation if needed, though often not required for simple cases
        # super().focusOutEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            # Global position required for correct offset calculation with frameless window
            self.offset = event.globalPos() - self.pos()
            event.accept() # Indicate the event was handled
            
    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & Qt.LeftButton:
            # Move using global positions
            self.move(event.globalPos() - self.offset)
            event.accept()
            
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
            event.accept()

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
        """Recursively clears all widgets and sub-layouts from a layout."""
        if layout is not None:
            while layout.count():
                item = layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    # If it's a widget, remove it from layout and delete it
                    widget.setParent(None)
                    widget.deleteLater()
                else:
                    # If it's a layout item, recursively clear the sub-layout
                    sub_layout = item.layout()
                    if sub_layout is not None:
                        self._clear_layout(sub_layout)
                    
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
            self.scoreLabel.setText("-")
            self.statusLabel.setText("No match selected or data available")
            self.statusLabel.show()
            self._clear_tables()
            # Add placeholder rows if desired
            self._add_placeholder_row(self.battingLayout, self._create_batter_row("No batting data", "-", "-", "-", "-", "-"))
            self._add_placeholder_row(self.bowlingLayout, self._create_bowler_row("No bowling data", "-", "-", "-", "-", "-"))
            self.adjustSize()
            return

        title = match_info.get('title', 'N/A')
        batting_score = match_info.get('score', 'N/A') 
        opponent_score = match_info.get('opponent_score')
        status = match_info.get('status', '')
        is_complete = match_info.get('is_complete', False)
        pom = match_info.get('pom') # Player of the Match
        team1_name = match_info.get('team1_name')
        team2_name = match_info.get('team2_name')

        # --- Update Header ---
        self.titleLabel.setText(title)

        # --- Update Score Display ---
        score_display = batting_score # Default to the main score
        if is_complete and opponent_score:
            # For completed matches, show both scores if available
            score_display = f"{batting_score} | {opponent_score}"
            self.statusLabel.setText(status) # Show final result
            if pom: # Add POM if available
                self.statusLabel.setText(f"{status}\nPOM: {pom}")
            self.statusLabel.show()
        elif opponent_score:
            # Live match with opponent score known (likely first innings completed)
            score_display = f"{batting_score} vs {opponent_score}"
            self.statusLabel.setText(status) # Show current status (e.g., need X runs)
            self.statusLabel.show()
        else:
            # Live match, only current batting score known, or status is the main info
            score_display = batting_score
            if status:
                 self.statusLabel.setText(status)
                 self.statusLabel.show()
            else:
                 self.statusLabel.hide() # Hide status if it's empty

        self.scoreLabel.setText(score_display)

        # --- Update Batter/Bowler Tables ---
        self._clear_tables()
        batters = match_info.get('batters', [])
        bowlers = match_info.get('bowlers', [])

        if batters:
            for batter in batters:
                name = self._abbreviate_name(batter.get('name', '-'))
                row = self._create_batter_row(
                    name,
                    batter.get('runs', '-'), 
                    batter.get('balls', '-'),
                    batter.get('fours', '-'),
                    batter.get('sixes', '-'),
                    batter.get('sr', '-')
                )
                self.battingLayout.addWidget(row)
        else:
            self._add_placeholder_row(self.battingLayout, self._create_batter_row("No batting data", "-", "-", "-", "-", "-"))

        if bowlers:
            for bowler in bowlers:
                name = self._abbreviate_name(bowler.get('name', '-'))
                row = self._create_bowler_row(
                    name,
                    bowler.get('overs', '-'), 
                    bowler.get('maidens', '-'), 
                    bowler.get('runs', '-'), 
                    bowler.get('wickets', '-'),
                    bowler.get('economy', '-')
                )
                self.bowlingLayout.addWidget(row)
        else:
             self._add_placeholder_row(self.bowlingLayout, self._create_bowler_row("No bowling data", "-", "-", "-", "-", "-"))

        self.adjustSize() # Adjust size after updating content

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
        self._detailed_widget = None # Use this for the detailed view widget
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

            # Handle minimized view separately first
            if self.is_minimized_view and self.selected_match_info:
                if self._mini_widget and self._mini_widget.isVisible():
                    self._mini_widget.hide()
                else:
                    # Ensure mini widget exists if match is selected
                    if not self._mini_widget:
                        self.show_minimized_view()
                    elif self._mini_widget:
                        self._mini_widget.show()
                        self._mini_widget.activateWindow()
                return # Handled minimized view toggle

            # --- Detailed View Logic --- 
            if not self.selected_match_info:
                # If no match is selected, maybe show a placeholder or message
                logging.info("Tray clicked, but no match selected.")
                if not self._detailed_widget or not self._detailed_widget.isVisible():
                    self.show_detailed_view() # Shows the "No match selected" message
                else:
                    self.hide_detailed_view()
                return
                
            # Ensure detailed widget exists if a match is selected
            if self._detailed_widget is None:
                 self._detailed_widget = ScoreFlyoutWidget() # Create if needed
                 # We need to update it immediately after creation
                 self._detailed_widget.update_score(self.selected_match_info)

            # Now, check pinned state for detailed view
            if self._detailed_widget._is_pinned:
                # If pinned, toggle visibility
                logging.debug("Toggle visibility for PINNED detailed view")
                self.toggle_detailed_view()
            else:
                # If unpinned, always show (and bring to front)
                logging.debug("Show UNPINNED detailed view (like a popup)")
                # Check visibility to avoid unnecessary work if already shown and active
                if not self._detailed_widget.isVisible() or not self._detailed_widget.isActiveWindow():
                    self.show_detailed_view() # This handles positioning, update, show, activate
                else:
                     # It's already visible and likely active, maybe just ensure activation
                     self._detailed_widget.activateWindow()
                     
        elif reason == QSystemTrayIcon.ActivationReason.Context: # Right-click
            logging.info("Tray icon right-clicked (Context) - menu shown automatically.")
            # Menu is shown automatically by Qt
            
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            logging.info("Tray icon double-clicked.")
            # Optional: Toggle between minimized and detailed view if a match is selected
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
        
        # Clean up the detailed widget if it exists
        if self._detailed_widget:
            self._detailed_widget.close()
            self._detailed_widget = None
            
        # Clean up the minimized widget if it exists
        if self._mini_widget:
            self._mini_widget.close()
            self._mini_widget = None
        self.mini_update_timer.stop()
        
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
            
            # Update the detailed widget if it's visible
            if self._detailed_widget and self._detailed_widget.isVisible():
                self._detailed_widget.update_score(self.selected_match_info)
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
                self.show_detailed_view()
        else:
            logging.warning(f"Selected match has no URL: {match_info.get('title')}")
            self.tray_icon.showMessage("Error", "Cannot get details for this match.", QSystemTrayIcon.Warning, 2000)

    # --- Renamed Flyout Activation to Detailed View Activation ---
    def toggle_detailed_view(self):
        if self._detailed_widget and self._detailed_widget.isVisible():
            self.hide_detailed_view()
        else:
            self.show_detailed_view()

    def show_detailed_view(self):
        """Shows the draggable detailed score widget."""
        if not self.selected_match_info:
            logging.warning("Cannot show detailed view: No match selected")
            # Maybe show a message or default state?
            if self._detailed_widget is None:
                 self._detailed_widget = ScoreFlyoutWidget() # Use the modified class
            self._detailed_widget.update_score({'title': 'No match selected', 'score': 'Select a match from the menu'})
        else:
             if self._detailed_widget is None:
                 self._detailed_widget = ScoreFlyoutWidget() # Use the modified class
             # Update content before showing
             self._detailed_widget.update_score(self.selected_match_info)

        # Position near cursor or tray icon
        try:
            tray_pos = self.tray_icon.geometry().center()
            screen_geometry = QApplication.desktop().availableGeometry(tray_pos)
            widget_size = self._detailed_widget.sizeHint() # Use sizeHint or fixed size
            x = tray_pos.x() - widget_size.width() // 2
            y = tray_pos.y() - widget_size.height() # Position above tray icon
            
            # Keep within screen bounds
            x = max(screen_geometry.left(), min(x, screen_geometry.right() - widget_size.width()))
            y = max(screen_geometry.top(), min(y, screen_geometry.bottom() - widget_size.height()))
            
            self._detailed_widget.move(x, y)
        except Exception as e:
            logging.warning(f"Could not position detailed widget near tray: {e}. Using cursor pos.")
            cursor_pos = QCursor.pos()
            self._detailed_widget.move(cursor_pos.x() - 150, cursor_pos.y() - 50) # Fallback position
            
        self._detailed_widget.show()
        logging.info("Detailed score widget shown.")


    def hide_detailed_view(self):
        """Hides the draggable detailed score widget."""
        if self._detailed_widget:
            self._detailed_widget.hide()
            logging.debug("Hiding detailed widget.")
            # Don't set to None here, allow toggling back

    def toggle_view_mode(self):
        """Toggle between minimized and detailed view modes."""
        self.is_minimized_view = not self.is_minimized_view
        logging.info(f"Toggled view mode. Minimized: {self.is_minimized_view}")
        
        # Update the menu
        self.populate_menu()
        
        # If we have a selected match, update the view
        if self.selected_match_info:
            # Hide current views first
            self.hide_detailed_view()
            if self._mini_widget:
                self._mini_widget.close()
                self._mini_widget = None

            # Show the appropriate view
            if self.is_minimized_view:
                self.show_minimized_view()
            else:
                self.show_detailed_view()
                
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
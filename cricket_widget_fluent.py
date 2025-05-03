# cricket_widget_fluent.py

# --- Imports ---
import sys
import time
import threading
import logging
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageQt # Need ImageQt for QPixmap conversion

# PyQt5 Imports
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QPoint, QSize
from PyQt5.QtGui import QIcon, QPixmap, QImage, QCursor
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QSystemTrayIcon, QMenu, QAction, QDesktopWidget

# Fluent Widgets Imports
from qfluentwidgets import setTheme, Theme, Flyout, FlyoutAnimationType, BodyLabel, CaptionLabel, FlyoutView, FlyoutViewBase, FlyoutAnimationManager # Import necessary components

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
    # ... (Full implementation from cricket_widget.py L:137-219) ...
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
        title_tag = soup.select_one('h1.cb-nav-hdr.cb-font- Mako , div.cb-match-header div.cb-col- Mako ')
        if title_tag:
            title = title_tag.get_text(strip=True)[:150]
        else:
             html_title = soup.find('title')
             if html_title: title = html_title.text.split('|')[0].strip()[:150]
        score_elements = soup.find_all("div", "cb-col cb-col-67 cb-scrs-wrp")
        if score_elements:
            score_parts = [elem.get_text(strip=True) for elem in score_elements]
            score = " | ".join(filter(None, score_parts))[:150]
        else:
             score = "N/A"
        status_tag = soup.select_one("div.cb-col.cb-col-100.cb-font-18.cb-toss-sts.cb-text-delay, div.cb-col.cb-col-100.cb-min-stts.cb-text-complete, div.cb-text-live, .cb-min-stts.cb-text-lunch, .cb-min-stts.cb-text-inningsbreak, .cb-text-preview")
        if status_tag: status_text = status_tag.get_text(strip=True)
        if status_text:
             if score == "N/A" or score == "": score = status_text[:150]
             elif status_text not in score: score = (score + f" ({status_text})")[:150]
        if title != "N/A" or score != "N/A":
             logging.info(f"Detailed score parsed: Title='{title}', Score='{score}'")
             return {'title': title, 'score': score}
        else:
             logging.warning(f"Could not parse detailed title/score from {url}")
             return None
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
        self.titleLabel = CaptionLabel("No match selected", self)
        self.scoreLabel = BodyLabel("-", self)

        # Basic layout
        self.vBoxLayout.setContentsMargins(10, 8, 10, 8)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.scoreLabel)
        self.vBoxLayout.addStretch(1) # Push content to top

        # Appearance
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.scoreLabel.setAlignment(Qt.AlignCenter)
        self.setFixedWidth(FLYOUT_WIDTH)
        self.setObjectName("ScoreFlyoutWidget") # For potential styling
        # Use fluent widget styles automatically via setTheme
        logging.info("ScoreFlyoutWidget initialized.")

    def update_score(self, match_info):
        """Updates the labels with new score data."""
        title = match_info.get('title', 'N/A')
        score = match_info.get('score', '-')
        logging.debug(f"Flyout updating score: Title='{title}', Score='{score}'")
        self.titleLabel.setText(title)
        self.scoreLabel.setText(score)
        self.adjustSize() # Adjust height based on content

# --- Main Application Class ---
class TrayApplication(QApplication):
    """Main application class managing tray icon and future UI."
"""
    def __init__(self, args):
        super().__init__(args)
        logging.info("Initializing TrayApplication (Fluent version)...")
        self.setQuitOnLastWindowClosed(False)
        global matches_data_cache
        matches_data_cache = []
        self.selected_match_info = None
        self._flyout_view = None
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
        self.trigger_refresh() # Start initial fetch
        self.tray_icon.show()
        logging.info("TrayApplication initialized and tray icon shown.")

    def populate_menu(self):
         """Populates the right-click context menu."""
         self.menu.clear()
         # Placeholder actions
         action_loading = self.menu.addAction("Loading matches...")
         action_loading.setEnabled(False)
         self.menu.addSeparator()
         refresh_action = self.menu.addAction("Refresh List")
         refresh_action.triggered.connect(self.trigger_refresh)
         self.menu.addSeparator()
         quit_action = self.menu.addAction("Exit")
         quit_action.triggered.connect(self.quit_app)

    def on_tray_activated(self, reason):
        """Handles tray icon activation (clicks)."""
        if reason == QSystemTrayIcon.ActivationReason.Trigger: # Left-click
            logging.info("Tray icon left-clicked (Trigger).")
            self.toggle_flyout()
        elif reason == QSystemTrayIcon.ActivationReason.Context: # Right-click
            logging.info("Tray icon right-clicked (Context) - menu shown automatically.")
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            # Optional: Treat double-click same as single click
            # logging.info("Tray icon double-clicked.")
            # self.toggle_flyout()
            pass

    def trigger_refresh(self):
         logging.info("Refresh triggered. Fetch logic TBD.")
         # TODO: Start/Restart homepage fetcher thread
         self.tray_icon.showMessage("Refresh", "Refreshing match list (not implemented)...", QSystemTrayIcon.Information, 1500)

    def quit_app(self):
        """Cleans up and quits the application."""
        logging.info("Quit triggered.")
        self.tray_icon.hide()
        # TODO: Stop threads here later
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
        # Only update the cached data. The flyout will be created with this data when shown.
        if self.selected_match_info:
             self.selected_match_info['score'] = score_data.get('score', self.selected_match_info.get('score'))
             # Update title as well, in case it changed (e.g., match status)
             self.selected_match_info['title'] = score_data.get('title', self.selected_match_info.get('title'))
             logging.debug(f"Updated selected_match_info cache: {self.selected_match_info}")
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
            self.selected_match_info = match_info # Store the whole dict
            # Don't update a non-existent persistent flyout here
            self.detailed_fetcher.set_url(url)
            if not self.detailed_fetcher.isRunning():
                self.detailed_fetcher.start()
            # Show the flyout
            self.show_flyout() # Will create a new flyout with current data
        else:
            logging.warning(f"Selected match has no URL: {match_info.get('title')}")
            self.tray_icon.showMessage("Error", "Cannot get details for this match.", QSystemTrayIcon.Warning, 2000)

    def trigger_refresh(self):
        logging.info("Refresh triggered.")
        self.tray_icon.setToolTip("Refreshing...")
        self.menu.clear()
        action = self.menu.addAction("Refreshing...")
        action.setEnabled(False)
        self.menu.addAction("Exit").triggered.connect(self.quit_app)
        if self.homepage_fetcher and self.homepage_fetcher.isRunning():
            self.homepage_fetcher.stop()
            self.homepage_fetcher.wait(500)
        self.homepage_fetcher = HomepageFetcher()
        self.homepage_fetcher.matches_updated.connect(self.handle_matches_update)
        self.homepage_fetcher.fetch_error.connect(self.handle_fetch_error)
        self.homepage_fetcher.start()

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

        # --- Create Flyout View --- #
        self._flyout_view = Flyout.make(
            flyout_content, # Pass the NEW content widget
            target=target_widget_for_pos,
            parent=self._dummy_target_widget, # Parent to dummy to manage lifetime?
            aniType=FlyoutAnimationType.FADE_IN
        )

        if self._flyout_view:
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
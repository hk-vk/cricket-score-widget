# cricket_widget.py

# --- Imports ---
import pystray
from PIL import Image
import time
import threading
import requests
from bs4 import BeautifulSoup
import sys
import logging

# --- Configuration ---
CRICBUZZ_URL = "https://www.cricbuzz.com/"
UPDATE_INTERVAL_SECONDS = 60  # Update every 60 seconds
ICON_PATH = "cricket_icon.ico"
LOG_FILE = "cricket_widget.log"
MAX_MATCHES_TOOLTIP = 3

# --- Logging Setup ---
logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global State ---
app_running = True
current_tooltip = "Fetching scores..."
tray_icon = None
matches_data = [] # List to hold {'title': '...', 'score': '...'} dictionaries
update_thread_instance = None

# --- Core Logic ---

def fetch_and_parse_cricbuzz():
    """Fetches Cricbuzz homepage and parses live scores."""
    logging.info("Attempting to fetch scores from Cricbuzz.")
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

        # --- Adapted Scraping Logic ---
        # Find match preview cards. Selectors might need adjustment if Cricbuzz changes layout.
        # This targets typical containers for live match scores on the homepage.
        match_elements = soup.select('div.cb-mtch-crd-rt-itm') # Look for match card items
        if not match_elements:
             # Try another potential selector structure if the first fails
             match_elements = soup.select('li[class*="cb-view-all-ga cb-match-card cb-bg-white"]')

        if not match_elements:
            logging.warning("Could not find live match elements using known selectors.")
            return [] # Return empty list if no matches found

        logging.info(f"Found {len(match_elements)} potential match elements.")

        for item in match_elements:
            title = "N/A"
            score = "N/A"
            status = ""

            # Extract Match Title (Team names etc.)
            title_tag = item.select_one('h3.cb-lv-scr-mtch-hdr') # Common header for matches
            if title_tag:
                title = title_tag.get_text(strip=True)
            else:
                 # Fallback for different card structures
                 title_tag_alt = item.select_one('div[class*="cb-card-match-title"] a')
                 if title_tag_alt:
                     title = title_tag_alt.get_text(strip=True)

            # Extract Score / Status
            # Cricbuzz uses various structures, try common ones
            score_div = item.select_one('div.cb-lv-scrs-col') # Often contains live score details
            if score_div:
                score = score_div.get_text(separator=" ", strip=True)
            else:
                # Fallback: Look for specific score/status elements if the main div isn't there
                status_tag = item.select_one('div[class*="cb-text-live"], div[class*="cb-text-complete"], span[class*="cb-text-preview"]')
                if status_tag:
                    status = status_tag.get_text(strip=True)

                # Try to find team scores separately if a combined score div wasn't found
                team1_score_tag = item.select_one('span.cb-lv-scrs-t1')
                team2_score_tag = item.select_one('span.cb-lv-scrs-t2')
                if team1_score_tag:
                    score = team1_score_tag.get_text(strip=True)
                    if team2_score_tag:
                        score += " | " + team2_score_tag.get_text(strip=True)
                elif status: # If we found a status but no score, use the status as score
                     score = status


            # Clean up title/score a bit
            title = ' '.join(title.split()) # Remove extra whitespace
            score = ' '.join(score.split()) # Remove extra whitespace

            # Skip if it doesn't look like a valid match entry
            if title == "N/A" and score == "N/A":
                logging.info("Skipping element, couldn't extract title or score.")
                continue

            live_matches_data.append({'title': title, 'score': score})
            logging.debug(f"Extracted Match: Title='{title}', Score='{score}'")

            if len(live_matches_data) >= MAX_MATCHES_TOOLTIP * 2: # Fetch a bit more than needed for tooltip, in case some are invalid later
                 logging.info(f"Reached fetch limit ({MAX_MATCHES_TOOLTIP * 2}).")
                 break
        # --- End Scraping Logic ---

        logging.info(f"Successfully parsed {len(live_matches_data)} matches.")
        return live_matches_data

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching Cricbuzz: {e}")
    except Exception as e:
        logging.error(f"Error parsing Cricbuzz HTML: {e}", exc_info=True) # Add traceback

    return [] # Return empty list on error

def format_tooltip(matches):
    """Formats the tooltip string from match data."""
    if not matches:
        return "No live matches found or error fetching."

    tooltip_parts = []
    for i, match in enumerate(matches):
        if i >= MAX_MATCHES_TOOLTIP:
            break
        tooltip_parts.append(f"{match.get('title', 'N/A')}: {match.get('score', 'N/A')}")

    return " | ".join(tooltip_parts)

def update_scores_tooltip():
    """Fetches scores and updates the tray icon tooltip."""
    global current_tooltip, matches_data
    logging.info("Running score update.")
    fetched_matches = fetch_and_parse_cricbuzz()
    # Only update global matches_data if fetch was successful (returned a list)
    if isinstance(fetched_matches, list):
         matches_data = fetched_matches
    current_tooltip = format_tooltip(matches_data)

    if tray_icon:
        tray_icon.title = current_tooltip
        logging.info(f"Tooltip updated: {current_tooltip}")
    else:
        logging.warning("Tray icon not available for tooltip update.")

def update_loop():
    """Background thread loop to periodically update scores."""
    global app_running
    while app_running:
        update_scores_tooltip()
        # Wait for the specified interval or until app_running is False
        for _ in range(UPDATE_INTERVAL_SECONDS):
            if not app_running:
                break
            time.sleep(1)
    logging.info("Update loop finished.")

# --- Tray Menu Actions ---

def on_refresh(icon, item):
    """Callback for manual refresh."""
    logging.info("Manual refresh triggered.")
    # Run update in a separate thread to avoid blocking the menu UI
    threading.Thread(target=update_scores_tooltip, daemon=True).start()

def on_quit(icon, item):
    """Callback for quitting the application."""
    global app_running, tray_icon
    logging.info("Quit triggered.")
    app_running = False
    if update_thread_instance:
        update_thread_instance.join(timeout=2) # Wait briefly for thread to exit
    if tray_icon:
        tray_icon.stop()
    logging.info("Application stopping.")
    # sys.exit(0) # pystray stop should handle exit

def create_menu():
    """Creates the dynamic pystray menu."""
    menu_items = []
    if not matches_data:
        menu_items.append(pystray.MenuItem("No matches loaded...", None, enabled=False))
    else:
        for match in matches_data:
             # Create a non-clickable item showing score detail
             display_text = f"{match.get('title', 'N/A')} - {match.get('score', 'N/A')}"
             menu_items.append(pystray.MenuItem(display_text, None, enabled=False))
        menu_items.append(pystray.Menu.SEPARATOR)

    menu_items.append(pystray.MenuItem("Refresh Now", on_refresh))
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.append(pystray.MenuItem("Exit", on_quit))

    return pystray.Menu(*menu_items)

# --- Main Setup ---

def main():
    global tray_icon, app_running, update_thread_instance

    logging.info("Application starting.")
    app_running = True

    try:
        icon_image = Image.open(ICON_PATH)
        logging.info(f"Icon '{ICON_PATH}' loaded successfully.")
    except FileNotFoundError:
        logging.error(f"Error: Icon file not found at '{ICON_PATH}'. Exiting.")
        print(f"Error: Icon file not found at '{ICON_PATH}'. Please create it.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
         logging.error(f"Error loading icon '{ICON_PATH}': {e}")
         print(f"Error loading icon '{ICON_PATH}': {e}", file=sys.stderr)
         sys.exit(1)

    # Create the tray icon instance
    # The menu is generated dynamically by the create_menu function
    tray_icon = pystray.Icon(
        'cricket_widget',
        icon_image,
        current_tooltip, # Initial tooltip
        menu=create_menu()
    )

    # Start the background update thread
    update_thread_instance = threading.Thread(target=update_loop, daemon=True)
    update_thread_instance.start()
    logging.info("Background update thread started.")

    # Run the tray icon application (blocking call)
    try:
        tray_icon.run()
    finally:
        # Ensure cleanup happens even if run() exits unexpectedly
        logging.info("pystray run() finished or interrupted.")
        app_running = False
        if update_thread_instance and update_thread_instance.is_alive():
             update_thread_instance.join(timeout=2)
        logging.info("Application finished.")

if __name__ == "__main__":
    main() 
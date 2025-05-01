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
    global matches_data
    logging.info("Attempting to fetch scores from Cricbuzz.")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(CRICBUZZ_URL, headers=headers, timeout=15)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        logging.info(f"Successfully fetched Cricbuzz homepage (Status: {response.status_code}).")
        soup = BeautifulSoup(response.text, 'html.parser')

        # --- Scraping Logic (Needs refinement based on current Cricbuzz HTML) ---
        # This part is highly dependent on Cricbuzz's website structure and might break.
        # We need to inspect the live site to find reliable selectors.
        # Placeholder logic - assuming a structure like list items for matches.
        live_matches = []
        # Example: Find a container div and then list items within it
        # match_elements = soup.select('div.live-matches-container > ul > li.match-item') # Fictional selector

        # --- !! Placeholder - Replace with actual scraping logic after inspection !! ---
        # For now, simulate finding some matches or indicating none found
        # if not match_elements:
        #     logging.warning("Could not find live match elements using current selectors.")
        #     return []

        # for item in match_elements:
        #     title_tag = item.select_one('.match-title') # Fictional
        #     score_tag = item.select_one('.match-score') # Fictional
        #     if title_tag and score_tag:
        #         live_matches.append({
        #             'title': title_tag.text.strip(),
        #             'score': score_tag.text.strip()
        #         })
        #     if len(live_matches) >= MAX_MATCHES_TOOLTIP: # Limit matches shown in tooltip
        #         break
        # --- End Placeholder --- 

        # Simulate finding matches for now
        if not matches_data: # Only add dummy data if empty
            live_matches = [
                {'title': 'IND vs AUS - T20', 'score': 'IND 180/5 (20 ov)'},
                {'title': 'ENG vs PAK - Test', 'score': 'ENG 350/7 (90 ov) - Stumps'},
                {'title': 'NZ vs SA - ODI', 'score': 'SA 120/2 (25.3 ov) - Need 130 more'}
            ]
            logging.info(f"Using placeholder match data.")
        else:
             live_matches = matches_data # Keep existing if refresh

        matches_data = live_matches
        logging.info(f"Parsed {len(matches_data)} matches.")
        return matches_data

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching Cricbuzz: {e}")
    except Exception as e:
        logging.error(f"Error parsing Cricbuzz HTML: {e}")

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
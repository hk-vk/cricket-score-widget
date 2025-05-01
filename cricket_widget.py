# cricket_widget.py

# --- Imports ---
import pystray
from PIL import Image, ImageDraw # Added ImageDraw for fallback icon
import time
import threading
import requests
from bs4 import BeautifulSoup
import sys
import logging
import tkinter as tk
from tkinter import ttk
import queue
import functools # Needed for menu item actions with arguments

# --- Configuration ---
CRICBUZZ_URL = "https://www.cricbuzz.com/"
UPDATE_INTERVAL_SECONDS = 120  # Update homepage matches less frequently now
DETAILED_UPDATE_INTERVAL_SECONDS = 15 # Update selected match score more often
ICON_PATH = "cricket_icon.ico"
LOG_FILE = "cricket_widget.log"
MAX_MATCHES_TOOLTIP = 3
MAX_MATCHES_MENU = 10 # Show more matches in the selection menu

# --- Logging Setup ---
logging.basicConfig(filename=LOG_FILE,
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# --- Global State ---
app_running = True
current_tooltip = "Fetching scores..."
tray_icon = None
matches_data = [] # List to hold {'title': '...', 'score': '...', 'url': '...'} dictionaries
update_thread_instance = None
detailed_update_thread = None # Thread for the selected match
selected_match_url = None
score_update_queue = queue.Queue() # Queue for tkinter updates

# Tkinter Globals
tk_root = None
detail_window = None
detail_title_var = None
detail_score_var = None

# --- Core Logic: Homepage Scraping ---

def fetch_and_parse_cricbuzz():
    """Fetches Cricbuzz homepage and parses live scores AND match URLs using user-provided selectors."""
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

        # --- Scraping Logic using user-provided selectors ---
        # Using find_all based on user's get_match example
        match_ul_list = soup.find_all("ul", "cb-col cb-col-100 videos-carousal-wrapper cb-mtch-crd-rt-itm")

        if not match_ul_list:
            logging.warning("Could not find the main match list UL element using selector: 'ul.cb-col.cb-col-100.videos-carousal-wrapper.cb-mtch-crd-rt-itm'")
            # As a fallback, try the previous selectors I used
            match_elements = soup.select('div.cb-mtch-crd-rt-itm')
            if not match_elements:
                 match_elements = soup.select('li[class*="cb-view-all-ga cb-match-card cb-bg-white"]')
            if match_elements:
                 logging.info("Falling back to previous homepage selectors.")
                 # (Re-implementing extraction for fallback path - simplified)
                 for item in match_elements:
                     url_tag = item.find('a', href=True)
                     if url_tag and url_tag['href'].startswith('/live-cricket-scores/'):
                        url = 'https://www.cricbuzz.com' + url_tag['href']
                        title = url_tag.get('title', item.get_text(strip=True))
                        score = item.select_one('div.cb-lv-scrs-col').get_text(strip=True) if item.select_one('div.cb-lv-scrs-col') else "N/A"
                        live_matches_data.append({'title': title, 'score': score, 'url': url})
                 return live_matches_data
            else:
                 return [] # Truly couldn't find anything

        match_count = 0
        # Iterate through the found UL elements (usually just one)
        for match_ul in match_ul_list:
            # Find all links within this UL
            for link_tag in match_ul.find_all("a", href=True):
                href = link_tag.get('href')
                title = link_tag.get('title', '').strip()
                link_text = link_tag.get_text(strip=True)

                # Check if it looks like a valid match link and has a title
                if href and href.startswith('/live-cricket-scores/') and title:
                    url = 'https://www.cricbuzz.com' + href

                    # Try to extract score from elements *within* the link tag if possible
                    score = "N/A" # Default score
                    score_div = link_tag.select_one('div.cb-lv-scrs-col') # Check for score div inside link
                    if score_div:
                        score = score_div.get_text(separator=" ", strip=True)
                    else: # Fallback: Check status text inside link
                        status_tag = link_tag.select_one('div[class*="cb-text-live"], div[class*="cb-text-complete"], span[class*="cb-text-preview"]')
                        if status_tag:
                           score = status_tag.get_text(strip=True)

                    score = ' '.join(score.split())
                    title = ' '.join(title.split())

                    live_matches_data.append({'title': title, 'score': score, 'url': url})
                    logging.debug(f"Extracted Match (User Method): Title='{title}', Score='{score}', URL='{url}'")
                    match_count += 1

                if match_count >= MAX_MATCHES_MENU:
                    logging.info(f"Reached menu match limit ({MAX_MATCHES_MENU}).")
                    break # Break inner loop
            if match_count >= MAX_MATCHES_MENU:
                 break # Break outer loop
        # --- End Scraping Logic ---

        logging.info(f"Successfully parsed {len(live_matches_data)} matches from homepage using user method (or fallback).")
        return live_matches_data

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching Cricbuzz homepage: {e}")
    except Exception as e:
        logging.error(f"Error parsing Cricbuzz homepage HTML: {e}", exc_info=True)

    return []

# --- Core Logic: Detailed Score Scraping ---

def fetch_detailed_score(url):
    """Fetches and parses the detailed score from a specific match page using user-provided selectors."""
    if not url:
        return None
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
        logging.debug(f"Successfully fetched match page: {url}")

        # --- Match Page Scraping Logic using user's commentary example selectors ---
        title = "N/A"
        score = "N/A"
        status_text = ""

        # Title: Attempt to find a reasonable title (user example didn't specify one for commentary page)
        # Keep previous attempts as fallbacks
        title_tag = soup.select_one('h1.cb-nav-hdr.cb-font- Mako ')
        if title_tag:
            title = title_tag.get_text(strip=True)
        else:
             title_tag = soup.select_one('div.cb-match-header div.cb-col- Mako ')
             if title_tag:
                 title = title_tag.get_text(strip=True)
             else: # Absolute fallback: Use HTML title tag
                  html_title = soup.find('title')
                  if html_title: title = html_title.text.split('|')[0].strip() # Get first part of title


        # Score: Using the primary selector from user's get_commentary example
        score_elements = soup.find_all("div", "cb-col cb-col-67 cb-scrs-wrp")
        if score_elements:
            # Combine text from all found score elements, might have multiple lines/teams
            score_parts = [elem.get_text(strip=True) for elem in score_elements]
            score = " | ".join(filter(None, score_parts)) # Join non-empty parts
        else:
             logging.warning(f"Could not find score using selector 'div.cb-col.cb-col-67.cb-scrs-wrp' on {url}")
             score = "N/A" # Explicitly mark as not found with this selector

        # Status/Delay: Using selectors from user's get_commentary
        delay_element = soup.find("div", "cb-col cb-col-100 cb-font-18 cb-toss-sts cb-text-delay")
        complete_element = soup.find("div", "cb-col cb-col-100 cb-min-stts cb-text-complete")
        live_element = soup.find("div", "cb-text-live") # Added this common one

        if delay_element:
            status_text = delay_element.get_text(strip=True)
        elif complete_element:
            status_text = complete_element.get_text(strip=True)
        elif live_element:
             status_text = live_element.get_text(strip=True)
        # Add other specific status checks if needed (lunch, innings break from previous attempt)
        elif soup.select_one('.cb-min-stts.cb-text-lunch, .cb-min-stts.cb-text-inningsbreak, .cb-text-preview'):
             status_tag = soup.select_one('.cb-min-stts.cb-text-lunch, .cb-min-stts.cb-text-inningsbreak, .cb-text-preview')
             if status_tag: status_text = status_tag.get_text(strip=True)

        # Combine score and status if appropriate
        if status_text:
             if score == "N/A" or score == "": score = status_text # Use status if score is missing
             elif status_text not in score: score += f" ({status_text})" # Append status

        title = ' '.join(title.split())
        score = ' '.join(score.split())

        if title != "N/A" or score != "N/A":
             logging.info(f"Detailed score parsed (User Method): Title='{title}', Score='{score}'")
             return {'title': title, 'score': score}
        else:
             logging.warning(f"Could not parse detailed title/score from {url} using user method selectors")
             return None
        # --- End Match Page Scraping Logic ---

    except requests.exceptions.RequestException as e:
        logging.error(f"Network error fetching detailed score from {url}: {e}")
    except Exception as e:
        logging.error(f"Error parsing detailed score HTML from {url}: {e}", exc_info=True)

    return None # Return None on error

# --- Tooltip Formatting ---
# Windows API limit for tooltips is 128 chars, we use 127 to be safe.
TOOLTIP_MAX_LEN = 127

def format_tooltip(matches):
    """Formats the tooltip string from match data, very strictly truncated."""
    if not matches:
        return "Fetching matches..."

    parts_to_join = []
    for i, match in enumerate(matches):
        if i >= MAX_MATCHES_TOOLTIP:
            break
        # Limit length of each part individually first to avoid huge strings
        title = match.get('title', 'N/A')[:50] # Limit title part
        score = match.get('score', 'N/A')[:50] # Limit score part
        parts_to_join.append(f"{title}: {score}")

    if not parts_to_join:
         return "No matches found."

    tooltip_string = " | ".join(parts_to_join)

    # Final truncation if the joined string is still too long
    if len(tooltip_string) > TOOLTIP_MAX_LEN:
        tooltip_string = tooltip_string[:TOOLTIP_MAX_LEN - 3] + "..."

    return tooltip_string

# --- Background Update Loops ---

def update_homepage_scores_loop():
    """Background thread loop to periodically update homepage scores for tooltip/menu."""
    global app_running, matches_data, current_tooltip
    while app_running:
        logging.info("Running homepage score update.")
        fetched_matches = fetch_and_parse_cricbuzz()
        if isinstance(fetched_matches, list):
             matches_data = fetched_matches # Update global list used by menu
             current_tooltip_raw = format_tooltip(matches_data)
             if tray_icon:
                 try:
                     # Aggressive Truncation: Always truncate before assignment
                     final_tooltip = current_tooltip_raw
                     if len(final_tooltip) > TOOLTIP_MAX_LEN:
                          logging.warning(f"Tooltip exceeded MAX_LEN ({TOOLTIP_MAX_LEN}) before assignment. Force truncating.")
                          final_tooltip = final_tooltip[:TOOLTIP_MAX_LEN - 3] + "..."
                     elif not final_tooltip: # Ensure tooltip is never empty
                          final_tooltip = " " # Use a single space if empty

                     # Log before setting title
                     log_tooltip = final_tooltip.replace("\n", "\\n").replace("\r", "\\r")
                     logging.debug(f"Attempting to set tooltip (len={len(final_tooltip)}): [{log_tooltip[:200]}{'...' if len(log_tooltip)>200 else ''}]")

                     tray_icon.title = final_tooltip
                     current_tooltip = final_tooltip # Update global state *after* successful assignment

                     # Update the menu itself when matches_data changes
                     tray_icon.menu = create_menu()
                     logging.info(f"Homepage matches updated. Tooltip set.")
                 except ValueError as e:
                      logging.error(f"ValueError setting tooltip: {e}. Tooltip was (len={len(final_tooltip)}): [{log_tooltip[:200]}{'...' if len(log_tooltip)>200 else ''}]")
                 except Exception as e:
                      logging.error(f"Unexpected error setting tooltip or menu: {e}", exc_info=True)
             else:
                 logging.warning("Tray icon not available for homepage update.")
        else:
             logging.warning("Homepage score fetch failed or returned invalid data.")

        # Wait for the specified interval or until app_running is False
        for _ in range(UPDATE_INTERVAL_SECONDS):
            if not app_running:
                break
            time.sleep(1)
    logging.info("Homepage update loop finished.")


def detailed_update_loop():
    """Background thread loop to periodically update score for the SELECTED match."""
    global app_running, selected_match_url, score_update_queue
    current_url = None
    while app_running:
        if selected_match_url:
            if selected_match_url != current_url:
                logging.info(f"Selected match changed to: {selected_match_url}")
                current_url = selected_match_url # Update local copy

            detailed_score_data = fetch_detailed_score(current_url)
            if detailed_score_data:
                try:
                    # Put data in queue for Tkinter thread
                    score_update_queue.put(detailed_score_data, block=False)
                    logging.debug(f"Put score update in queue: {detailed_score_data}")
                except queue.Full:
                    logging.warning("Score update queue is full. Skipping update.")
            else:
                 logging.warning(f"Failed to fetch detailed score for {current_url}")

            # Wait even if fetch failed or no URL selected currently
            sleep_interval = DETAILED_UPDATE_INTERVAL_SECONDS
        else:
            # No match selected, sleep longer before checking again
            current_url = None # Reset local copy
            sleep_interval = UPDATE_INTERVAL_SECONDS
            logging.debug("No match selected. Detailed update loop sleeping longer.")


        for _ in range(sleep_interval):
            if not app_running or selected_match_url != current_url: # Stop/Restart if app stops or URL changes
                break
            time.sleep(1)

    logging.info("Detailed score update loop finished.")


# --- Tkinter UI Functions ---

def create_detail_window():
    """Creates the persistent Tkinter window for detailed scores (initially hidden)."""
    global detail_window, detail_title_var, detail_score_var
    if detail_window is not None and detail_window.winfo_exists():
        logging.info("Detail window already exists.")
        return # Already created and exists

    logging.info("Creating detail score window.")
    detail_window = tk.Toplevel(tk_root)
    detail_window.title("Live Score")
    detail_window.geometry("320x100") # Slightly larger
    detail_window.resizable(False, False)
    # detail_window.attributes("-toolwindow", True) # Remove this for standard window feel
    detail_window.protocol("WM_DELETE_WINDOW", on_detail_window_close) # Handle close button

    # Basic Styling
    window_bg = "#f0f0f0" # Light grey background
    text_color = "#333333" # Dark grey text
    title_font = ('Segoe UI', 10, 'bold')
    score_font = ('Segoe UI', 12)

    detail_window.config(bg=window_bg)

    # Frame for content padding
    content_frame = ttk.Frame(detail_window, padding="10 10 10 10", style='Content.TFrame')
    content_frame.pack(expand=True, fill='both')

    # Style for the frame
    style = ttk.Style()
    style.configure('Content.TFrame', background=window_bg)

    detail_title_var = tk.StringVar(detail_window, "No match selected")
    detail_score_var = tk.StringVar(detail_window, "-")

    title_label = ttk.Label(
        content_frame,
        textvariable=detail_title_var,
        anchor="center",
        font=title_font,
        background=window_bg,
        foreground=text_color,
        wraplength=280 # Wrap long titles
    )
    title_label.pack(pady=(0, 5), fill='x')

    score_label = ttk.Label(
        content_frame,
        textvariable=detail_score_var,
        anchor="center",
        font=score_font,
        background=window_bg,
        foreground=text_color
    )
    score_label.pack(pady=(5, 0), fill='x')

    detail_window.withdraw() # Start hidden
    logging.info("Detail score window created and hidden.")

def update_detail_window_from_queue():
    """Checks the queue and updates the Tkinter detail window labels."""
    global detail_window, detail_title_var, detail_score_var
    try:
        while not score_update_queue.empty():
            score_data = score_update_queue.get_nowait()
            logging.debug(f"Got score data from queue: {score_data}")
            if detail_window and detail_title_var and detail_score_var:
                 # Check if window still exists before updating
                 if detail_window.winfo_exists():
                    detail_title_var.set(score_data.get('title', 'N/A'))
                    detail_score_var.set(score_data.get('score', 'N/A'))
                    logging.info(f"Detail window updated: {score_data.get('title')} - {score_data.get('score')}")
                 else:
                     logging.warning("Detail window does not exist, cannot update.")
                     # Clear queue if window is gone? Or let it drain? Drain for now.
            score_update_queue.task_done()

    except queue.Empty:
        pass # No updates pending
    except Exception as e:
        logging.error(f"Error updating detail window from queue: {e}", exc_info=True)

    # Reschedule this check
    if app_running and tk_root:
        tk_root.after(500, update_detail_window_from_queue) # Check queue every 500ms

def show_detail_window():
    """Makes the detail window visible or creates it if needed."""
    global detail_window
    # Ensure root exists
    if tk_root is None:
        logging.error("Cannot show detail window, Tk root does not exist.")
        return

    # Check if exists and is valid window
    if detail_window is None or not detail_window.winfo_exists():
        logging.warning("Detail window doesn't exist or was destroyed. Recreating.")
        create_detail_window()
        # If creation failed, detail_window might still be None
        if detail_window is None:
             logging.error("Failed to recreate detail window.")
             return

    logging.info("Showing detail window.")
    detail_window.deiconify()
    detail_window.lift() # Bring to front
    detail_window.focus_force() # Try to give focus


def hide_detail_window():
    """Hides the detail window."""
    # Don't deselect match here, only when explicitly closed by user or quit
    if detail_window and detail_window.winfo_exists():
        logging.info("Hiding detail window (withdraw).")
        detail_window.withdraw()

def on_detail_window_close():
    """Callback when the user closes the detail window. Hides and deselects."""
    global selected_match_url
    logging.info("Detail window close requested by user.")
    if detail_window and detail_window.winfo_exists():
        logging.info("Withdrawing detail window on close.")
        detail_window.withdraw()
    selected_match_url = None # Deselect match when window is explicitly closed
    logging.info("Match deselected due to window close.")


# --- Tray Menu Actions ---

def on_match_selected(match_info, icon=None, item=None):
    """Callback when a specific match is selected from the menu."""
    global selected_match_url, detailed_update_thread, detail_window, detail_title_var, detail_score_var
    logging.info(f"on_match_selected called with: {match_info}")

    # Check if Tkinter is initialized
    if tk_root is None:
        logging.error("Match selection ignored: Tkinter root not initialized.")
        return

    url = match_info.get('url')
    title = match_info.get('title', 'N/A')
    initial_score = match_info.get('score', 'Fetching...') # Use homepage score initially

    if not url:
        logging.error("Match selected, but no URL found in match_info.")
        return

    logging.info(f"Match selected: {title} ({url})")
    selected_match_url = url

    # Ensure window and vars exist before updating
    if detail_window and detail_window.winfo_exists() and detail_title_var and detail_score_var:
        logging.debug("Updating existing detail window variables.")
        detail_title_var.set(title)
        detail_score_var.set(initial_score)
    else:
        logging.warning("Detail window or its variables not ready during match selection. Will be updated by queue later.")
        if detail_window is None or not detail_window.winfo_exists():
             create_detail_window()

    logging.debug("Calling show_detail_window from on_match_selected.")
    show_detail_window()

    # Start or restart the detailed update thread
    if detailed_update_thread is None or not detailed_update_thread.is_alive():
        logging.info("Starting detailed update thread from on_match_selected.")
        detailed_update_thread = threading.Thread(target=detailed_update_loop, daemon=True)
        detailed_update_thread.start()
    else:
        logging.info("Detailed update thread already running (selection changed).")


def on_refresh(icon=None, item=None):
    """Callback for manual refresh of homepage matches."""
    logging.info("Manual refresh triggered (homepage list).")
    # Run update in a separate thread to avoid blocking the menu UI
    threading.Thread(target=update_homepage_scores_loop, daemon=True).start() # Rerun the main loop once

def on_quit(icon=None, item=None):
    """Callback for quitting the application."""
    global app_running, tray_icon, tk_root
    logging.info("Quit triggered.")
    app_running = False # Signal threads to stop

    # Stop threads (allow short time, non-blocking)
    if detailed_update_thread and detailed_update_thread.is_alive():
        logging.info("Waiting briefly for detailed update thread to stop...")
        detailed_update_thread.join(timeout=0.1)
    if update_thread_instance and update_thread_instance.is_alive():
         logging.info("Waiting briefly for homepage update thread to stop...")
         update_thread_instance.join(timeout=0.1)

    # Stop pystray
    if tray_icon:
        logging.info("Stopping pystray icon.")
        tray_icon.stop()

    # Stop Tkinter
    if tk_root:
        logging.info("Stopping Tkinter main loop.")
        tk_root.quit() # Stops mainloop
        # tk_root.destroy() # Optional: Destroy widgets

    logging.info("Application cleanup finished.")


def create_menu():
    """Creates the dynamic pystray menu with clickable match items."""
    menu_items = []

    # Add matches first, making them clickable
    if not matches_data:
        menu_items.append(pystray.MenuItem("Fetching matches...", None, enabled=False))
    else:
        added_matches = 0
        for match in matches_data:
            url = match.get('url')
            if url: # Only add if we have a URL to select
                 display_text = f"{match.get('title', 'N/A')}"
                 # Add score from homepage fetch if available
                 score_text = match.get('score', '')
                 if score_text and score_text != "N/A": display_text += f" - {score_text}"

                 # Use functools.partial to pass the specific match_info to the callback
                 action = functools.partial(on_match_selected, match)
                 menu_items.append(pystray.MenuItem(display_text, action))
                 added_matches += 1
            # Limit number shown in menu directly
            if added_matches >= MAX_MATCHES_MENU: break

        if added_matches == 0:
            menu_items.append(pystray.MenuItem("No live matches found", None, enabled=False))

    # Add Separator and controls
    menu_items.append(pystray.Menu.SEPARATOR)
    menu_items.append(pystray.MenuItem("Refresh List", on_refresh))
    menu_items.append(pystray.MenuItem("Exit", on_quit))

    return pystray.Menu(*menu_items)

# --- Left Click Action ---

def on_left_click(icon, item):
     """Callback for left-clicking the tray icon. Toggles detail window."""
     global detail_window
     logging.info("on_left_click called.")

     # Check if Tkinter is initialized
     if tk_root is None:
          logging.error("Left click ignored: Tkinter root not initialized.")
          return

     # Check if window exists and is currently visible ('normal' state)
     try:
         # Check exists first to avoid errors if destroyed
         window_exists = detail_window and detail_window.winfo_exists()
         is_visible = window_exists and detail_window.state() == 'normal'
         logging.debug(f"Left click: window_exists={window_exists}, is_visible={is_visible}")

         if is_visible:
             logging.info("Detail window visible, hiding on left click.")
             hide_detail_window()
         else:
             # Window either hidden, iconified, or not created yet
             logging.info("Detail window hidden or not created, showing on left click.")
             show_detail_window() # Handles creation if needed

     except Exception as e:
         logging.error(f"Error during on_left_click: {e}", exc_info=True)


# --- Main Setup ---

def main():
    global tray_icon, app_running, update_thread_instance, tk_root, score_update_queue

    logging.info("Application starting.")
    app_running = True

    # --- Initialize Tkinter ---
    try:
        logging.info("Initializing Tkinter...")
        tk_root = tk.Tk()
        tk_root.withdraw() # Hide the main root window
        # Set up style if needed (optional)
        style = ttk.Style()
        # Try common themes for a slightly more modern look
        available_themes = style.theme_names()
        logging.debug(f"Available ttk themes: {available_themes}")
        if 'vista' in available_themes:
             style.theme_use('vista')
             logging.info("Using 'vista' ttk theme.")
        elif 'clam' in available_themes:
             style.theme_use('clam')
             logging.info("Using 'clam' ttk theme.")
        elif 'xpnative' in available_themes:
             style.theme_use('xpnative')
             logging.info("Using 'xpnative' ttk theme.")
        # Initialize Queue
        score_update_queue = queue.Queue()
        # Create the hidden detail window
        create_detail_window()
        # Start the queue checker loop in Tkinter thread
        tk_root.after(100, update_detail_window_from_queue)
        logging.info("Tkinter initialized successfully.")
    except Exception as e:
        logging.error(f"Failed to initialize Tkinter: {e}", exc_info=True)
        print("Error: Failed to initialize GUI components. Exiting.", file=sys.stderr)
        sys.exit(1)


    # --- Load Icon ---
    icon_image = None
    try:
        icon_image = Image.open(ICON_PATH)
        logging.info(f"Icon '{ICON_PATH}' loaded successfully.")
    except FileNotFoundError:
        logging.warning(f"Icon file not found at '{ICON_PATH}'. Using default icon.")
    except Exception as e:
        logging.warning(f"Error loading icon '{ICON_PATH}': {e}. Using default icon.")

    if icon_image is None:
        try:
            width, height = 64, 64
            icon_image = Image.new('RGB', (width, height), color = 'darkgreen') # Dark green fallback
            draw = ImageDraw.Draw(icon_image)
            # Simple "C"
            draw.text((width//4, height//4), "C", fill="white", font_size=32)
            logging.info("Created default fallback icon.")
        except Exception as e:
            logging.error(f"Could not create default fallback icon: {e}")
            pass # Continue without image object if creation fails


    # --- Create Tray Icon ---
    try:
        logging.info("Creating pystray icon...")
        tray_icon = pystray.Icon(
            'cricket_widget',
            icon_image,
            current_tooltip,
            menu=create_menu(), # Right-click menu
            left_click_action=on_left_click # Assign left-click action
        )
        logging.info("pystray icon created with left-click action.")
    except Exception as e:
         logging.error(f"Failed to create pystray icon: {e}", exc_info=True)
         print("Error: Failed to create system tray icon. Exiting.", file=sys.stderr)
         on_quit() # Attempt cleanup
         sys.exit(1)


    # --- Start Background Threads ---
    logging.info("Starting background threads...")
    # Start homepage update loop
    update_thread_instance = threading.Thread(target=update_homepage_scores_loop, daemon=True)
    update_thread_instance.start()
    logging.info("Homepage update thread started.")

    # Start pystray icon thread
    pystray_thread = threading.Thread(target=tray_icon.run, daemon=True)
    pystray_thread.start()
    logging.info("Pystray thread started.")

    # Detailed thread will be started on match selection

    # --- Run Tkinter Main Loop (Blocks Main Thread) ---
    logging.info("Starting Tkinter main loop.")
    try:
        tk_root.mainloop()
    except KeyboardInterrupt:
         logging.info("KeyboardInterrupt received.")
    finally:
        logging.info("Tkinter main loop finished.")
        # Ensure cleanup is called if mainloop exits unexpectedly
        if app_running: # Check if quit wasn't already called
             on_quit()

if __name__ == "__main__":
    main() 
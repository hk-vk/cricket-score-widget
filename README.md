# Cricket Score Widget (Fluent UI)

A simple system tray widget for Windows that displays live cricket scores from Cricbuzz, built with PyQt5 and PyQt-Fluent-Widgets.


## Features

*   Fetches live match list from Cricbuzz homepage.
*   Displays detailed scores for a selected match in a draggable, always-on-top window.
*   Includes batting and bowling scorecards.
*   Shows match status (live, completed, result, Player of the Match).
*   Optional minimized view for a compact score display.
*   Pinning feature to keep the detailed widget always on top.
*   Option to automatically start the widget when Windows starts.
*   Modern UI using PyQt-Fluent-Widgets.

## Usage (For Users)

1.  **Download:** Go to the [**Releases Page**](https://github.com/hk-vk/cricket-score-widget/releases) on GitHub.
2.  Download the latest `CricketWidget.exe` file from the Assets section of the most recent release.
3.  **Run:** Double-click the downloaded `CricketWidget.exe` file to start the application.
4.  **Tray Icon:** A cricket icon will appear in your system tray (notification area).
5.  **Select Match:** Right-click the tray icon to see a list of current matches. Click on a match to view its detailed score.
6.  **View Options:**
    *   **Detailed View:** Left-click the tray icon (when a match is selected) to show/hide the detailed score widget.
        *   Use the pin icon (📌/➖) in the widget to toggle the always-on-top behavior.
        *   Drag the widget by clicking and holding anywhere on its background.
        *   If unpinned, the widget hides when it loses focus.
    *   **Minimized View:** Right-click the tray icon and select "Minimized View". This shows a very small, draggable score overlay.
        *   Click the expand button (□) on the minimized view to switch back to the detailed view mode.
        *   Click the close button (×) to hide the minimized view.
7.  **Auto-Start:** Right-click the tray icon and check/uncheck "Start with Windows" to enable/disable automatically launching the widget when you log in.
8.  **Exit:** Right-click the tray icon and select "Exit".

## Development Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/hk-vk/cricket-score-widget.git
    cd cricket-score-widget
    ```
2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # Activate the environment
    # Windows (Command Prompt/PowerShell):
    .\venv\Scripts\activate
    # macOS/Linux:
    # source venv/bin/activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run the script:**
    ```bash
    python cricket_widget_fluent.py
    ```

## Building the Executable (Optional)

If you want to build the `.exe` yourself:

1.  Make sure you have the development environment set up (including `PyInstaller` installed via `requirements.txt`).
2.  Ensure `cricket_icon.ico` is present in the root directory.
3.  Run PyInstaller:
    ```bash
    pyinstaller --name CricketWidget --onefile --windowed --icon=cricket_icon.ico cricket_widget_fluent.py
    ```
4.  The executable will be located in the `dist` folder (`dist/CricketWidget.exe`).

## Contributing

Contributions, issues, and feature requests are welcome!

## License

[MIT](LICENSE) <!-- Optional: Add a LICENSE file --> 
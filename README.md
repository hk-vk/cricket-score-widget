# Cricket Score Widget (Electron + React)

A simple system tray widget for Windows that displays live cricket scores from Cricbuzz, built with Electron, React, and Vite.

## Features

*   Fetches live match list from Cricbuzz homepage.
*   Displays detailed scores for a selected match in a draggable, always-on-top window.
*   Includes batting and bowling scorecards (when available).
*   Shows match status (live, completed, result, Player of the Match).
*   Pinning feature to keep the widget always on top.
*   Light/Dark theme toggling.
*   Auto-refreshes match list and detailed scores.

## Usage (For Users)

1.  **Download:** Go to the [**Releases Page**](https://github.com/hk-vk/cricket-score-widget/releases) on GitHub.
2.  Download the latest `CricketWidget Setup X.Y.Z.exe` file from the Assets section of the most recent release.
3.  **Run Setup:** Double-click the downloaded setup file and follow the installation prompts.
4.  **Launch:** After installation, the widget should start automatically. If not, find it in your Start Menu.
5.  **Tray Icon:** A cricket icon will appear in your system tray (notification area).
6.  **Select Match:** Right-click the tray icon to see a list of current matches. Click on a match to view its detailed score in the main window.
7.  **Window Interaction:**
    *   **Show/Hide:** Left-click the tray icon or right-click and select "Show/Hide" to toggle the main window's visibility.
    *   **Pinning:** Use the pin icon (📌/➖) in the widget's header to toggle the always-on-top behavior. If unpinned, the widget hides when it loses focus.
    *   **Dragging:** Drag the widget by clicking and holding anywhere on its header/background.
    *   **Toggle View:** Right-click the tray icon and select "Toggle View" to switch between the match list and detailed score (if a match is selected).
    *   **Toggle Theme:** Right-click the tray icon and select "Toggle Theme" to switch between light and dark modes.
8.  **Refresh:** Right-click the tray icon and select "Refresh Data" to manually update the match list.
9.  **Exit:** Right-click the tray icon and select "Quit".

## Development Setup

1.  **Prerequisites:**
    *   Node.js (version 20 or later recommended)
    *   pnpm (Install via `npm install -g pnpm`)
2.  **Clone the repository:**
    ```bash
    git clone https://github.com/hk-vk/cricket-score-widget.git
    cd cricket-score-widget
    ```
3.  **Install dependencies:**
    ```bash
    pnpm install
    ```
4.  **Run the development server:**
    ```bash
    pnpm run dev
    ```
    This will start the Vite development server for the React frontend and launch the Electron application.

## Building the Application

To build the application for distribution (creates an installer in the `release` folder):

1.  Ensure development dependencies are installed (`pnpm install`).
2.  Run the distribution command:
    ```bash
    pnpm dist
    ```
3.  The installer (`CricketWidget Setup X.Y.Z.exe`) will be located in the `release` folder.

## Contributing

Contributions, issues, and feature requests are welcome!

## License

This project is licensed under the ISC License. See the `LICENSE` file for details (if included). 
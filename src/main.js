const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, screen } = require('electron');
const path = require('node:path');
const axios = require('axios');
const cheerio = require('cheerio');

// --- Constants ---
const CRICBUZZ_URL = 'https://www.cricbuzz.com/';
const MAX_MATCHES_MENU = 10;
const UPDATE_INTERVAL_SECONDS = 120;
const DETAILED_UPDATE_INTERVAL_SECONDS = 5;
const isDev = process.env.NODE_ENV !== 'production';

// --- Window Size & Positioning ---
const WINDOW_WIDTH = 280;
const WINDOW_HEIGHT = 350;
const MARGIN_X = 10;
const MARGIN_Y = 10;

let tray = null;
let mainWindow = null;
let currentMatchUrl = null;
let matchesCache = [];
let currentTheme = 'dark'; // Default theme
let selectedMatchLiveScore = null; // Variable to store the live score string
let staticIconPath = null; // Store path to original icon
let defaultTrayIcon = null; // Store default NativeImage

// --- Team Name Abbreviation Helper ---
const teamAbbreviations = {
  "Punjab Kings": "PBKS",
  "Lucknow Super Giants": "LSG",
  "Gujarat Titans": "GT",
  "Rajasthan Royals": "RR",
  "Royal Challengers Bengaluru": "RCB", // Updated name
  "Sunrisers Hyderabad": "SRH",
  "Kolkata Knight Riders": "KKR",
  "Delhi Capitals": "DC",
  "Chennai Super Kings": "CSK",
  "Mumbai Indians": "MI",
  // Add other IPL/International teams as needed
  "India": "IND",
  "Australia": "AUS",
  "England": "ENG",
  "South Africa": "SA",
  "New Zealand": "NZ",
  "Pakistan": "PAK",
  "Sri Lanka": "SL",
  "West Indies": "WI",
  "Bangladesh": "BAN",
  "Afghanistan": "AFG",
  "Ireland": "IRE",
  "Zimbabwe": "ZIM",
};

function shortenTeamNames(title) {
  if (!title) return 'N/A';
  let shortTitle = title;
  // Replace full names with abbreviations
  for (const [fullName, abbr] of Object.entries(teamAbbreviations)) {
    // Use regex to replace whole words only to avoid partial matches
    const regex = new RegExp(`\\b${fullName}\\b`, 'gi');
    shortTitle = shortTitle.replace(regex, abbr);
  }
  // Remove extra details like "Live Cricket Score", "Commentary"
  shortTitle = shortTitle.replace(/,.*?- Live Cricket Score, Commentary/, '');
  shortTitle = shortTitle.replace(/,.*?- Scorecard.*/, ''); // Handle Scorecard variation
  shortTitle = shortTitle.replace(/\|.*/, ''); // Remove anything after a pipe (often site name)
  // Keep match number info if present, e.g., ", 54th Match"
  const matchInfoMatch = title.match(/,\s*(\d+(st|nd|rd|th)\s+Match)/i);
  if (matchInfoMatch && !shortTitle.includes(matchInfoMatch[1])) {
      // Find the "vs" part to append match info correctly
      const vsIndex = shortTitle.indexOf(' vs ');
      if (vsIndex !== -1) {
          const teamsPart = shortTitle.substring(0, shortTitle.indexOf(',', vsIndex) !== -1 ? shortTitle.indexOf(',', vsIndex) : shortTitle.length);
          shortTitle = `${teamsPart}, ${matchInfoMatch[1]}`;
      } else {
           shortTitle += `, ${matchInfoMatch[1]}`; // Fallback append
      }

  }
   // Trim potential leading/trailing commas or whitespace
  return shortTitle.replace(/^,\s*|\s*,\s*$/g, '').trim();
}

// --- Function to create score icon --- 
/* Commenting out dynamic icon generation for now
function createScoreIcon(textToDisplay) {
  const size = 32; 
  const padding = 2; 
  const rectSize = size - padding * 2;
  const borderRadius = 4; 
  
  let displayedText = textToDisplay.replace(/\s+/g, ' ').trim(); 

  const winMatch = displayedText.match(/^(.+?)\s+won\b/i); 
  if (winMatch) {
    displayedText = `${shortenTeamNames(winMatch[1])} won`; 
  }

  displayedText = displayedText.substring(0, 15);
  
  const svgString = `
    <svg width="${size}" height="${size}" xmlns="http://www.w3.org/2000/svg">
      <style>
        .background {
          fill: rgba(100, 100, 100, 0.85); /* Neutral gray background */
          stroke: rgba(220, 220, 220, 0.6); /* Light gray border */
          stroke-width: 1;
        }
        .score { 
          font: bold 10px Arial, sans-serif; 
          fill: white; /* Keep text white */
          text-anchor: middle; 
          dominant-baseline: central;
        }
      </style>
      <rect x="${padding}" y="${padding}" width="${rectSize}" height="${rectSize}" rx="${borderRadius}" ry="${borderRadius}" class="background" />
      <text x="50%" y="55%" class="score">${displayedText}</text>
    </svg>
  `;
  
  const dataUrl = `data:image/svg+xml;base64,${Buffer.from(svgString).toString('base64')}`;
  try {
      const scoreIcon = nativeImage.createFromDataURL(dataUrl);
      return scoreIcon;
  } catch (e) {
      console.error("Error creating NativeImage from Data URL:", e);
      return defaultTrayIcon; 
  }
}
*/

// --- Function to Update Tray Tooltip ONLY ---
function updateTrayTooltip(textToDisplay) {
  if (tray) {
    if (textToDisplay && typeof textToDisplay === 'string' && textToDisplay.trim() !== 'N/A' && textToDisplay.trim() !== '') {
      // Update Tooltip (use the original full text for tooltip)
      const cleanText = textToDisplay.replace(/\s+/g, ' ').trim(); 
      let truncatedText = cleanText.substring(0, 60); 
      if (cleanText.length > 60) {
        truncatedText += '...';
      }
      tray.setToolTip(`Cricket: ${truncatedText}`);
    } else {
      // Reset to default tooltip
      tray.setToolTip('Cricket Widget'); 
    }
  }
}

// --- Scraping Functions ---
async function fetchAndParseCricbuzz() {
  const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/'
  };

  try {
    console.log("Attempting to fetch homepage matches from Cricbuzz.");
    const response = await axios.get(CRICBUZZ_URL, { headers, timeout: 20000 });
    const $ = cheerio.load(response.data);
    const liveMatchesData = [];
    let matchCount = 0;

    // Try primary selector first
    let matchElements = $("ul.cb-col.cb-col-100.videos-carousal-wrapper.cb-mtch-crd-rt-itm");
    
    if (matchElements.length === 0) {
      // Fallback selectors
      matchElements = $('div.cb-mtch-crd-rt-itm');
      if (matchElements.length === 0) {
        matchElements = $('li[class*="cb-view-all-ga cb-match-card cb-bg-white"]');
      }
    }

    matchElements.each((_, matchUl) => {
      if (matchCount >= MAX_MATCHES_MENU) return false; // Break loop

      $(matchUl).find('a[href^="/live-cricket-scores/"]').each((_, linkTag) => {
        if (matchCount >= MAX_MATCHES_MENU) return false;

        const href = $(linkTag).attr('href');
        const originalTitle = $(linkTag).attr('title') || $(linkTag).text().trim();

        if (href && originalTitle) {
          const url = 'https://www.cricbuzz.com' + href;
          let score = 'N/A';

          // Try to find score
          const scoreDiv = $(linkTag).find('div.cb-lv-scrs-col');
          if (scoreDiv.length) {
            score = scoreDiv.text().trim();
          } else {
            const statusTag = $(linkTag).find('div[class*="cb-text-live"], div[class*="cb-text-complete"], span[class*="cb-text-preview"]');
            if (statusTag.length) {
              score = statusTag.text().trim();
            }
          }

          // --- Shorten Title ---
          const shortTitle = shortenTeamNames(originalTitle);
          // --- End Shorten Title ---

          liveMatchesData.push({
            title: shortTitle.substring(0, 100),
            score: score.substring(0, 100),
            url: url
          });
          matchCount++;
        }
      });
    });

    console.log(`Successfully parsed ${liveMatchesData.length} matches from homepage.`);
    matchesCache = liveMatchesData;
    return liveMatchesData;
  } catch (error) {
    console.error('Error fetching/parsing Cricbuzz homepage:', error);
    return [];
  }
}

async function fetchDetailedScore(url) {
  if (!url) return null;

  const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': CRICBUZZ_URL
  };

  try {
    console.log(`Attempting to fetch detailed score from: ${url}`);
    const response = await axios.get(url, { headers, timeout: 15000 });
    const $ = cheerio.load(response.data);

    // Initialize result object
    const result = {
      title: 'N/A',
      score: 'N/A',
      opponent_score: null,
      status: '',
      batters: [],
      bowlers: [],
      team1_name: null,
      team2_name: null,
      pom: null,
      is_complete: false
    };

    // Extract title and team names
    let originalTitleText = 'N/A';
    const titleTag = $('h1.cb-nav-hdr, div.cb-nav-main h1');
    if (titleTag.length) {
      originalTitleText = titleTag.text().trim();
    } else {
      const htmlTitle = $('title');
      if (htmlTitle.length) {
        originalTitleText = htmlTitle.text(); // Keep potential extra info for parsing
      }
    }

    // --- Shorten Title ---
    result.title = shortenTeamNames(originalTitleText).substring(0, 150); // Use shortened title for display
    // --- End Shorten Title ---

    // Parse team names from ORIGINAL title before shortening for better accuracy
    const vsMatch = originalTitleText.match(/^(.*?) vs (.*?)(?:,|$)/); // Adjusted regex
    if (vsMatch) {
      result.team1_name = teamAbbreviations[vsMatch[1].trim()] || vsMatch[1].trim(); // Abbreviate if possible
      result.team2_name = teamAbbreviations[vsMatch[2].trim()] || vsMatch[2].trim(); // Abbreviate if possible
      console.log(`Parsed teams: ${result.team1_name} vs ${result.team2_name}`);
    }

    // Score and Status Extraction
    const scoreWrapper = $('div.cb-scrs-wrp');
    const statusElement = $('div.cb-min-stts');

    if (scoreWrapper.length) {
      const teamScores = scoreWrapper.find('div.cb-min-tm');
      if (teamScores.length === 2) {
        // Likely a completed or between-innings state
        result.is_complete = true;
        const score1 = $(teamScores[0]).text().trim();
        const score2 = $(teamScores[1]).text().trim();

        // Use abbreviated names for matching if they exist
        const team1Check = result.team1_name || "Team1";
        const team2Check = result.team2_name || "Team2";

        if (score1.includes(team1Check)) {
          result.score = score1;
          result.opponent_score = score2;
        } else if (score2.includes(team1Check)) {
          result.score = score2;
          result.opponent_score = score1;
        } else if (score1.includes(team2Check)) { // Check against team 2 if team 1 didn't match
             result.score = score1; // Assuming score1 belongs to team2 if score1 contains team2 name
             result.opponent_score = score2;
        } else if (score2.includes(team2Check)) {
             result.score = score2; // Assuming score2 belongs to team2 if score2 contains team2 name
             result.opponent_score = score1;
        } else { // Fallback if names don't match abbreviations well
          result.score = score1;
          result.opponent_score = score2;
        }

        // Check completion status
        if (statusElement.length) {
          const statusText = statusElement.text().trim();
          result.status = statusText;
          const completionIndicators = ['won by', 'draw', 'tied', 'no result'];
          result.is_complete = completionIndicators.some(indicator => 
            statusText.toLowerCase().includes(indicator));
        }
      } else if (teamScores.length === 1) {
        // Live match, one team batting
        result.is_complete = false;
        const battingScoreRaw = $(teamScores[0]).text().trim();
        
        // Try to find opponent score
        const opponentScoreTag = scoreWrapper.find('div.cb-text-gray');
        if (opponentScoreTag.length) {
          result.opponent_score = opponentScoreTag.text().trim();
        }

        // Assign batting score - prioritize abbreviated names if available
        const team1Check = result.team1_name || "Team1";
        const team2Check = result.team2_name || "Team2";
        if (battingScoreRaw.includes(team1Check)) {
          result.score = battingScoreRaw;
         } else if (battingScoreRaw.includes(team2Check)) {
          result.score = battingScoreRaw;
        } else {
             result.score = battingScoreRaw; // Fallback
        }
      }
    }

    let displayValue = null;
    if (result.is_complete && result.status && result.status !== 'N/A') {
        displayValue = result.status; 
    } else if (result.score && result.score !== 'N/A') {
        displayValue = result.score; 
    }
    
    selectedMatchLiveScore = displayValue; 
    updateTrayTooltip(selectedMatchLiveScore); // Update tooltip only

    // Player of the Match
    if (result.is_complete) {
      const pomItem = $('div.cb-mom-itm');
      if (pomItem.length) {
        const pomLabel = pomItem.find('span.cb-text-gray');
        const pomNameTag = pomItem.find('a.cb-link-undrln');
        if (pomLabel.length && 
            pomLabel.text().trim().includes('PLAYER OF THE MATCH') && 
            pomNameTag.length) {
          result.pom = pomNameTag.text().trim();
        }
      }
    }

    // Extract Batters and Bowlers if needed
    // (This part can be implemented if you want to show detailed stats)

    console.log('Successfully parsed detailed score data');
    return result;
  } catch (error) {
    console.error('Error fetching detailed score:', error);
    selectedMatchLiveScore = null;
    updateTrayTooltip(null); // Update tooltip only on error
    return null;
  }
}

// --- IPC Handlers ---
ipcMain.handle('fetch-matches', async () => {
  try {
    return await fetchAndParseCricbuzz();
  } catch (error) {
    console.error('Error in fetch-matches handler:', error);
    return [];
  }
});

ipcMain.handle('fetch-detailed-score', async (_, url) => {
  try {
    return await fetchDetailedScore(url);
  } catch (error) {
    console.error('Error in fetch-detailed-score handler:', error);
    return null;
  }
});

ipcMain.on('select-match', (_, url) => {
  console.log(`Match selected/deselected: ${url}`);
  currentMatchUrl = url; 
  if (!url) {
    selectedMatchLiveScore = null;
    updateTrayTooltip(null); // Update tooltip only
  }
});

// --- Window Creation ---
function createWindow() {
  console.log('Creating main window...');

  // Define window dimensions
  const windowWidth = WINDOW_WIDTH;
  const windowHeight = WINDOW_HEIGHT;

  mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    fullscreenable: false,
    resizable: false,
    movable: true,
    transparent: true,
    backgroundColor: '#00000000',
    opacity: 1.0,
    roundedCorners: false, // Keep corners sharp
    hasShadow: false,
    thickFrame: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: !isDev,
      defaultFontFamily: {
        standard: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Oxygen, Ubuntu, Cantarell, Open Sans, Helvetica Neue, sans-serif',
      },
      defaultBackgroundColor: '#00000000',
      experimentalFeatures: true
    }
  });

  // Set additional transparency
  mainWindow.setBackgroundColor('#00000000');

  // Remove any frame or borders
  mainWindow.setAutoHideMenuBar(true);
  
  // --- Set position AFTER creating the window ---
  try {
    const primaryDisplay = screen.getPrimaryDisplay();
    const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
    const xPos = screenWidth - windowWidth;
    const yPos = screenHeight - windowHeight - MARGIN_Y;
    console.log(`Screen workArea: ${screenWidth}x${screenHeight}, Calculated Pos: ${xPos},${yPos}`);
    mainWindow.setPosition(xPos, yPos, false); // false = no animation
  } catch (e) {
    console.error("Error getting screen info or setting position:", e);
    // Fallback position if screen info fails
    mainWindow.center();
  }
  // --- End position setting ---
  
  // Make window always fully transparent
  mainWindow.once('ready-to-show', () => {
    mainWindow.setBackgroundColor('#00000000');
    mainWindow.show(); // Show normally, don't maximize
  });

  mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
    console.error(`Failed to load window content: ${errorDescription} (Code: ${errorCode})`);
  });

  mainWindow.webContents.on('did-finish-load', () => {
    console.log('Window content finished loading.');
  });

  // Load the index.html of the app.
  if (isDev) {
    const devUrl = 'http://localhost:5173';
    console.log(`Loading URL for dev: ${devUrl}`);
    mainWindow.loadURL(devUrl);
  } else {
    const prodPath = path.join(__dirname, '../dist/index.html');
    console.log(`Loading file for prod: ${prodPath}`);
    mainWindow.loadFile(prodPath);
  }

  // Emitted when the window is closed.
  mainWindow.on('closed', () => {
    // Dereference the window object, usually you would store windows
    // in an array if your app supports multi windows, this is the time
    // when you should delete the corresponding element.
    mainWindow = null;
  });

  // Optional: Hide the window when it loses focus
  // mainWindow.on('blur', () => {
  //   if (!mainWindow.webContents.isDevToolsOpened()) {
  //     mainWindow.hide();
  //   }
  // });

  return mainWindow; // Return the created window instance
}

// Function to ensure the window exists and toggle its visibility
function toggleWindow() {
  console.log('toggleWindow called');
  if (mainWindow && !mainWindow.isDestroyed()) {
    if (mainWindow.isVisible()) {
      console.log('Hiding window');
      mainWindow.hide();
    } else {
      console.log('Showing window');
      // Recalculate position just before showing
      try {
        const primaryDisplay = screen.getPrimaryDisplay();
        const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
        const [currentWidth, currentHeight] = mainWindow.getSize(); // Use actual size
        const xPos = screenWidth - currentWidth;
        const yPos = screenHeight - currentHeight - MARGIN_Y;
        console.log(`Screen workArea (toggle): ${screenWidth}x${screenHeight}, Calculated Pos: ${xPos},${yPos}`);
        mainWindow.setPosition(xPos, yPos, false);
      } catch (e) {
          console.error("Error recalculating position:", e);
      }
      mainWindow.show();
      mainWindow.focus();
    }
  } else {
    console.log('Window not found or destroyed, creating new one.');
    createWindow(); // Creates and positions the window
    mainWindow.once('ready-to-show', () => {
      console.log('Newly created window ready to show');
      // Position is already set in createWindow
      mainWindow.show();
    });
  }
}

function createTray() {
  const iconName = 'cricket_icon.ico';

  if (isDev) {
    staticIconPath = path.resolve(__dirname, '..', 'public', iconName);
  } else {
    staticIconPath = path.resolve(app.getAppPath(), '..', 'public', iconName);
  }

  console.log(`Attempting to load static tray icon from: ${staticIconPath}`); 

  defaultTrayIcon = nativeImage.createFromPath(staticIconPath); // Create default icon
  if (!defaultTrayIcon || defaultTrayIcon.isEmpty()) {
    console.error(`Failed to load static tray icon. Please check the path: ${staticIconPath}`);
    return; 
  }
  
  tray = new Tray(defaultTrayIcon); // Use the default icon initially

  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Show/Hide',
      click: toggleWindow, // Use the new toggle function
    },
    {
      label: 'Refresh Data',
      click: async () => {
        try {
          await fetchAndParseCricbuzz(); // Fetch data
          mainWindow?.webContents.send('refresh-data'); // Notify renderer
        } catch (error) {
            console.error('Error during manual refresh:', error);
        }
      },
    },
    {
      label: 'Toggle View',
      click: () => {
        mainWindow?.webContents.send('toggle-view');
      },
    },
    {
      label: 'Toggle Theme',
      click: () => {
        currentTheme = currentTheme === 'dark' ? 'light' : 'dark';
        console.log(`Theme toggled to: ${currentTheme}`);
        mainWindow?.webContents.send('set-theme', currentTheme);
      },
    },
    {
      label: 'Quit',
      click: () => {
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Cricket Widget'); // Initial tooltip
  tray.setContextMenu(contextMenu);
  tray.on('click', toggleWindow);
}

// --- App Lifecycle ---
app.whenReady().then(() => {
  createWindow(); // Create the initial window (hidden)
  createTray();

  // Start periodic updates for the match list
  setInterval(async () => {
    try {
      // Only fetch list if no match is selected
      if (!currentMatchUrl) { 
        console.log('Periodic refresh triggered for match list.');
        await fetchAndParseCricbuzz();
        // Send refresh signal ONLY if list is potentially visible
        mainWindow?.webContents.send('refresh-data'); 
      }
    } catch(error) {
        console.error('Error during periodic list refresh:', error);
    }
  }, UPDATE_INTERVAL_SECONDS * 1000);

  // Start periodic updates for the SELECTED match details (more frequent)
  setInterval(async () => {
    if (mainWindow && currentMatchUrl) { // Only run if window exists and a match is selected
      try {
        console.log(`Periodic refresh triggered for selected match: ${currentMatchUrl}`);
        const details = await fetchDetailedScore(currentMatchUrl);
        // Send updated details to renderer if needed (optional, depends on UI needs)
        if (details) {
          mainWindow.webContents.send('update-selected-details', details); // Send updated details
        }
      } catch (error) {
        console.error(`Error during periodic detail refresh for ${currentMatchUrl}:`, error);
      }
    }
  }, DETAILED_UPDATE_INTERVAL_SECONDS * 1000); // Use the more frequent interval

  app.on('activate', () => {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) {
        // Check if mainWindow is null or destroyed before creating
        if (!mainWindow || mainWindow.isDestroyed()) {
          createWindow();
        } else {
          // If it exists but is hidden, show it
          if (!mainWindow.isVisible()) {
            mainWindow.show();
          }
          mainWindow.focus();
        }
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

// Ensure only one instance runs
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', (event, commandLine, workingDirectory) => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

// Handle webSecurity for Vite HMR in dev
if (isDev) {
  app.commandLine.appendSwitch('disable-features', 'OutOfBlinkCors');
}
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
const WINDOW_HEIGHT = 350; // Default height for list view
const WINDOW_HEIGHT_DETAIL = 320; // Height for detail view
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
let initialWindowPositionForDrag = null; // Store window position at drag start
let isWindowPinned = true; // Track pinned state in main, default true

// --- ADDED: Player Name Formatting Helper ---
function formatPlayerName(fullName) {
  if (!fullName || typeof fullName !== 'string') return 'N/A';
  const parts = fullName.trim().split(/\s+/); // Split by whitespace
  if (parts.length === 1) return parts[0]; // Return single name as is
  const firstNameInitial = parts[0].charAt(0).toUpperCase();
  const lastName = parts[parts.length - 1];
  return `${firstNameInitial}. ${lastName}`;
}
// --- END ADDED ---

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
// Commenting out dynamic icon generation for now
/*
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
          fill: rgba(100, 100, 100, 0.85); // Neutral gray background
          stroke: rgba(220, 220, 220, 0.6); // Light gray border
          stroke-width: 1;
        }
        .score { 
          font: bold 10px Arial, sans-serif; 
          fill: white; // Keep text white
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
            // Try different status indicators but limit to THIS match container only
            // First, get the closest container that should only contain this match
            const matchContainer = $(linkTag).closest('li, .cb-mtch-blk, .cb-mtch-itm, .cb-srs-mtchs-tm');
            
            // Look for status indicators only within this specific match container
            const statusSelectors = [
              'div[class*="cb-text-live"]',
              'div[class*="cb-text-complete"]', 
              'span[class*="cb-text-preview"]',
              'div.cb-text-rain',
              'div.cb-text-stump',
              'div.cb-text-lunch',
              'div.cb-text-tea',
              'div.cb-text-innings-break'
            ];
            
            let statusFound = false;
            for (const selector of statusSelectors) {
              // Only search within this match's container
              const statusTag = matchContainer.find(selector).first();
              if (statusTag.length && !statusTag.closest('a').length) { // Avoid status inside other links
                score = statusTag.text().trim();
                statusFound = true;
                break;
              }
            }
            
            // Check for completed match result - only for this specific match
            if (!statusFound) {
              const resultTag = matchContainer.find('div.cb-text-complete').first();
              if (resultTag.length && resultTag.text().includes('won')) {
                const resultText = resultTag.text().trim();
                // Extract the winning team and margin - making sure it's for this match
                
                // Connect result with match title for validation
                const originalTeams = shortenTeamNames(originalTitle).split(' vs ');
                const resultContainsTeam = originalTeams.some(team => 
                  resultText.includes(team) || resultText.includes(team.split(' ')[0]));
                
                if (resultContainsTeam) {
                  const wonMatch = resultText.match(/(.+?)\s+won\s+by\s+(.+)/i);
                  if (wonMatch) {
                    const winningTeam = shortenTeamNames(wonMatch[1].trim());
                    const margin = wonMatch[2].trim();
                    score = `${winningTeam} won by ${margin}`;
                  } else {
                    score = resultText; // Use full status text if pattern doesn't match
                  }
                }
              }
            }
          }

          // If score is still N/A, try to fetch status directly from the match URL
          if (score === 'N/A' || !score) {
            // Extract info from URL parts
            const matchIdMatch = href.match(/\/live-cricket-scores\/(\d+)\//);
            if (matchIdMatch) {
              const matchId = matchIdMatch[1];
              // Try to extract meaningful info from the URL itself
              const matchType = href.includes('test') ? 'Test match' : 
                               href.includes('odi') ? 'ODI' :
                               href.includes('t20') ? 'T20' : '';
              
              // Check title for match stage information
              if (originalTitle.includes('Preview')) {
                score = 'Match Preview';
              } else if (originalTitle.includes('Report')) {
                score = 'Match Report';
              } else if (href.includes('upcoming')) {
                score = 'Upcoming match';
              } else {
                // Look for other meaningful info like date or time
                const dateElement = matchContainer.find('div.cb-font-12').first();
                if (dateElement.length) {
                  // Make sure this date is not inside another match container
                  if (dateElement.closest('li, .cb-mtch-blk, .cb-mtch-itm').is(matchContainer)) {
                    score = dateElement.text().trim();
                  }
                } else {
                  // Just extract teams as fallback
                  const teams = shortenTeamNames(originalTitle).split(' vs ');
                  if (teams.length === 2) {
                    score = `${teams[0]} v ${teams[1]}`;
                    if (matchType) {
                      score += ` (${matchType})`;
                    }
                  }
                }
              }
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
      score: 'N/A', // Current batting team score or primary score line
      opponent_score: null, // Opponent score (usually from completed innings)
      status: '', // Match status (e.g., Live, Result, Stumps)
      batters: [], // Array of { name, runs, balls, fours, sixes, sr, isStriker }
      bowlers: [], // Array of { name, overs, maidens, runs, wickets, eco, isCurrent }
      team1_name: null,
      team2_name: null,
      pom: null,
      is_complete: false,
      recent_balls: null // Store recent balls string if available
    };

    // Extract title and team names
    let originalTitleText = 'N/A';
    const titleTag = $('h1.cb-nav-hdr, div.cb-nav-main h1');
    if (titleTag.length) {
      originalTitleText = titleTag.text().trim();
    } else {
      const htmlTitle = $('title');
      if (htmlTitle.length) {
        originalTitleText = htmlTitle.text();
      }
    }

    result.title = shortenTeamNames(originalTitleText).substring(0, 150);

    const vsMatch = originalTitleText.match(/^(.*?) vs (.*?)(?:,|$)/);
    if (vsMatch) {
      result.team1_name = teamAbbreviations[vsMatch[1].trim()] || vsMatch[1].trim();
      result.team2_name = teamAbbreviations[vsMatch[2].trim()] || vsMatch[2].trim();
      console.log(`Parsed teams: ${result.team1_name} vs ${result.team2_name}`);
    }

    // Score and Status Extraction - Improved approach to get accurate status
    const scoreWrapper = $('div.cb-scrs-wrp');
    
    // Extract match status - try different selectors in priority order
    const statusSelectors = [
      // Primary status selectors - most reliable
      'div.cb-text-inprogress', 
      'div.cb-text-live',
      'div.cb-text-complete',
      'div.cb-min-stts',
      // Specific situations
      'div.cb-text-rain',
      'div.cb-text-lunch',
      'div.cb-text-tea',
      'div.cb-text-drinks',
      'div.cb-text-stump',
      'div.cb-text-innings-break',
      // Generic fallbacks
      'div[class*="cb-text-"]',
      'span.cb-text-gray'
    ];
    
    let statusFound = false;
    
    // Try selectors in order (from most specific to most generic)
    for (const selector of statusSelectors) {
      const statusElement = $(selector);
      if (statusElement.length) {
        const statusText = statusElement.text().trim();
        // Ignore very short status texts or those that don't look like status
        if (statusText.length > 2 && !statusText.match(/^(\d+|[a-z]+)$/i)) {
          result.status = statusText;
          statusFound = true;
          break;
        }
      }
    }

    // Analyze if match is complete
    if (statusFound) {
      const completionIndicators = ['won by', 'draw', 'tied', 'no result', 'abandoned', 'complete'];
      result.is_complete = completionIndicators.some(indicator =>
        result.status.toLowerCase().includes(indicator));
    }

    // Check specific status patterns based on team names to avoid mixing up status
    if (result.is_complete && result.team1_name && result.team2_name) {
      // Validate that status mentions one of the teams
      if (result.status.includes(result.team1_name) || 
          result.status.includes(result.team2_name) ||
          (result.team1_name.length > 3 && result.status.includes(result.team1_name.substring(0, 3))) ||
          (result.team2_name.length > 3 && result.status.includes(result.team2_name.substring(0, 3)))) {
        // Status is valid as it mentions a team from the match
      } else {
        // Status doesn't mention either team, might be generic or incorrect
        console.log(`Status doesn't mention either team, might need validation: ${result.status}`);
      }
    }
    
    // Extract Scores - this should work for both completed and live matches
    const teamScores = scoreWrapper.find('div.cb-min-tm'); 
    if (teamScores.length >= 1) {
      result.score = $(teamScores[0]).text().trim();
      if (teamScores.length === 2) {
        result.opponent_score = $(teamScores[1]).text().trim();
      }
    } else {
      // Alternative: try extracting from live score area
      const liveScoreTag = scoreWrapper.find('div.cb-min-bat-rw span.cb-font-20.text-bold');
      if (liveScoreTag.length) {
        result.score = liveScoreTag.text().trim();
      }
      
      // Try to find opponent score
      const opponentScoreTag = scoreWrapper.find('div.cb-text-gray, h2.cb-text-gray.cb-font-16.text-normal');
      if (opponentScoreTag.length) {
        result.opponent_score = opponentScoreTag.text().trim();
      }
    }
    
    // Player of the Match (for completed matches)
    if (result.is_complete) {
      const pomItem = $('div.cb-mom-itm');
      if (pomItem.length) {
        const pomLabel = pomItem.find('span.cb-text-gray');
        const pomNameTag = pomItem.find('a.cb-link-undrln');
        if (pomLabel.length && pomLabel.text().trim().includes('PLAYER OF THE MATCH') && pomNameTag.length) {
          result.pom = pomNameTag.text().trim();
        }
      }
    }
    
    // Extract Batters
    const batterTable = $('div.cb-min-inf:has(div.cb-min-hdr-rw:contains(Batter))');
    batterTable.find('div.cb-min-itm-rw').each((_, row) => {
      const nameTag = $(row).find('div.cb-col-50 a');
      const name = nameTag.text().trim();
      const isStriker = $(row).find('div.cb-col-50').text().includes('*'); // Check for asterisk
      const cols = $(row).find('div.cb-col');
      if (cols.length >= 6) { // Name, R, B, 4s, 6s, SR
        const runs = parseInt($(cols[1]).text().trim(), 10);
        const balls = parseInt($(cols[2]).text().trim(), 10);
        const fours = $(cols[3]).text().trim();
        const sixes = $(cols[4]).text().trim();

        // Calculate SR
        let strikeRate = '0.00';
        if (!isNaN(runs) && !isNaN(balls) && balls > 0) {
          strikeRate = ((runs / balls) * 100).toFixed(2);
        }

        result.batters.push({
          name: formatPlayerName(name), // Use formatted name
          runs: runs.toString(),
          balls: balls.toString(),
          fours: fours,
          sixes: sixes,
          strikeRate: strikeRate,
          isStriker: isStriker
        });
      }
    });

    // Extract Bowlers
    const bowlerTable = $('div.cb-min-inf:has(div.cb-min-hdr-rw:contains(Bowler))');
    bowlerTable.find('div.cb-min-itm-rw').each((_, row) => {
      const nameTag = $(row).find('div.cb-col-50 a');
      const name = nameTag.text().trim();
      const isCurrent = $(row).find('div.cb-col-50').text().includes('*'); // Check for asterisk
      const cols = $(row).find('div.cb-col');
      if (cols.length >= 6) { // Name, O, M, R, W, ECO
        const oversText = $(cols[1]).text().trim();
        const maidens = $(cols[2]).text().trim();
        const runsConceded = parseInt($(cols[3]).text().trim(), 10);
        const wickets = $(cols[4]).text().trim();

        // Calculate Econ
        let economyRate = '0.00';
        const oversParts = oversText.split('.');
        const fullOvers = parseInt(oversParts[0], 10);
        const ballsBowled = oversParts.length > 1 ? parseInt(oversParts[1], 10) : 0;

        if (!isNaN(runsConceded) && !isNaN(fullOvers) && !isNaN(ballsBowled)) {
          const totalBalls = fullOvers * 6 + ballsBowled;
          if (totalBalls > 0) {
            economyRate = ((runsConceded / totalBalls) * 6).toFixed(2);
          }
        }

        result.bowlers.push({
          name: formatPlayerName(name),
          overs: oversText,
          maidens: maidens,
          runs: runsConceded.toString(),
          wickets: wickets,
          economy: economyRate,
          isCurrent: isCurrent
        });
      }
    });
    
    // Extract Recent Balls
    const recentBallsTag = $('div.cb-min-rcnt span:not(.text-bold)');
    if (recentBallsTag.length) {
      result.recent_balls = recentBallsTag.text().trim();
    }

    // Update Tray Tooltip Logic (remains the same)
    let displayValue = null;
    if (result.is_complete && result.status && result.status !== 'N/A') {
      displayValue = result.status;
    } else if (result.score && result.score !== 'N/A') {
      displayValue = result.score;
    }
    selectedMatchLiveScore = displayValue;
    updateTrayTooltip(selectedMatchLiveScore); // Update tooltip only

    console.log('Successfully parsed detailed score data');
    // console.log(JSON.stringify(result, null, 2)); // Optional: Log the full result for debugging
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
    updateTrayTooltip(null);
  }

  // No longer resizing the window when selecting a match
  // This keeps the window at its current size
});

// --- ADDED: Always on Top Handler ---
ipcMain.on('set-always-on-top', (_, isPinned) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    console.log(`Setting Always on Top to: ${isPinned}`);
    mainWindow.setAlwaysOnTop(isPinned, 'screen-saver'); 
    isWindowPinned = isPinned; // Update the tracked state
  }
});
// --- END ADDED ---

// --- Window Creation ---
function createWindow() {
  console.log('Creating main window...');

  // Use a single consistent window size that works for both views
  // This height is sized to fit both match list and match detail views
  const windowWidth = WINDOW_WIDTH;
  const windowHeight = 400; // Use a taller window to fit both match list and details

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
    roundedCorners: true, // Enable rounded corners for the window
    hasShadow: true, // Re-enable shadow for depth
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

  // --- ADDED: Hide on Blur if Unpinned ---
  mainWindow.on('blur', () => {
    // Only hide if the window exists, isn't dev tools focused, and is NOT pinned
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.webContents.isDevToolsOpened() && !isWindowPinned) {
      console.log('Window blurred and is unpinned. Hiding.');
      mainWindow.hide();
    } else {
      console.log('Window blurred but kept visible (pinned or devtools open).');
    }
  });
  // --- END ADDED ---

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
      
      // Show window at its current size and position
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
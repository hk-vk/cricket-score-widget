import { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, screen } from 'electron'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import axios from 'axios'
import * as cheerio from 'cheerio'
import fs from 'node:fs'
import isDev from 'electron-is-dev'

// Get __dirname equivalent in ESM
const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

// --- Constants ---
const CRICBUZZ_URL = 'https://www.cricbuzz.com/';
const MAX_MATCHES_MENU = 10;
const UPDATE_INTERVAL_SECONDS = 120;
const DETAILED_UPDATE_INTERVAL_SECONDS = 5;

// --- Window Size & Positioning ---
const WINDOW_WIDTH = 280;
const WINDOW_HEIGHT = 400; // Default height for full view
const WINDOW_HEIGHT_MINIMIZED = 110; // Even smaller height for minimized view (just score and status)
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

// Add after other constants
let previousSelectedMatchState = {};
let previousEventByUrl = {};
let processedCommentaryByUrl = {}; // Track processed commentary to avoid showing the same delivery twice
let lastEventTimeByUrl = {}; // Track last event time to prevent rapid repeats

// Helper function to extract wicket count from score
function extractWicketCount(score) {
  if (!score) return null;
  const match = score.match(/\/(\d+)/);
  return match ? parseInt(match[1], 10) : null;
}

// Helper function to detect boundary or wicket from commentary
function detectEventFromCommentary(commentary) {
  if (!commentary) return null;
  const lowerComm = commentary.toLowerCase();
  console.log(`[EventDetect] Checking commentary: "${lowerComm}"`);

  // Check for boundary terms (more specific first)
  if (lowerComm.includes('four') || 
      lowerComm.includes('4 runs') || 
      lowerComm.includes('4!') || 
      lowerComm.includes('4 !')) {
    console.log('[EventDetect] FOUR detected from commentary.');
    return 'four';
  }
  
  if (lowerComm.includes('six') || 
      lowerComm.includes('6 runs') || 
      lowerComm.includes('6!') || 
      lowerComm.includes('6 !')) {
    console.log('[EventDetect] SIX detected from commentary.');
    return 'six';
  }

  // Check for wicket-related terms
  const wicketTerms = [
    'out caught', 'c & b', 'caught & bowled', 'run out', 
    'bowled', 'caught', 'lbw', 'stumped', 'retired hurt', 
    'hit wicket', ' out', ',out', 'out!', 'wicket!', 'dismissed'
  ];
  if (wicketTerms.some(term => lowerComm.includes(term))) {
    console.log('[EventDetect] WICKET detected from commentary.');
    return 'wicket';
  }

  console.log('[EventDetect] No specific event detected from commentary.');
  return null;
}

// Helper function to check if enough time has passed since last event
function canTriggerNewEvent(url, eventType) {
  const now = Date.now();
  const lastEventTime = lastEventTimeByUrl[url]?.[eventType] || 0;
  const minTimeBetweenEvents = 2000; // 2 seconds minimum between same type of events
  
  if (now - lastEventTime >= minTimeBetweenEvents) {
    if (!lastEventTimeByUrl[url]) {
      lastEventTimeByUrl[url] = {};
    }
    lastEventTimeByUrl[url][eventType] = now;
    return true;
  }
  return false;
}

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
            // Get the closest match-specific container
            const matchContainer = $(linkTag).closest('li, .cb-mtch-blk, .cb-mtch-itm, .cb-srs-mtchs-tm');
            
            // Extract match teams from title for validation
            const matchTeams = shortenTeamNames(originalTitle).split(' vs ');
            const team1 = matchTeams[0]?.trim();
            const team2 = matchTeams.length > 1 ? matchTeams[1]?.trim() : '';
            
            // Extract status - ONLY if it's within this match container and not within another match
            let statusText = '';
            const statusSelectors = [
              '.cb-text-complete',   // Match completed/result
              '.cb-text-live',       // Live match
              '.cb-text-preview',    // Match preview
              '.cb-text-rain',       // Rain delay
              '.cb-text-stump',      // Stumps
              '.cb-text-lunch',      // Lunch break
              '.cb-text-tea',        // Tea break
              '.cb-text-innings-break', // Innings break
              '.cb-text-drinks',     // Drinks break
              '.cb-text-delayed',    // Delayed start
              '.cb-text-abandoned',  // Abandoned match
              '.cb-min-stts',        // General status container
              '[class*="cb-text-"]'  // Catch-all for other status classes
            ];
            
            // First try to find a specific status within this match container
            for (const selector of statusSelectors) {
              if (matchContainer && matchContainer.length) {
                const statusElements = matchContainer.find(selector);
                if (statusElements.length) {
                  // Found a match-specific status
                  statusElements.each((_, el) => {
                    const elText = $(el).text().trim();
                    // Make sure this text actually relates to this match and not another
                    if (elText) {
                      // Check if this status is associated with this match
                      // by verifying it's not part of another match link
                      const isInAnotherLink = $(el).closest('a[href*="/live-cricket-scores/"]').length > 0 && 
                        !$(el).closest('a[href*="/live-cricket-scores/"]').is(linkTag);
                      
                      if (!isInAnotherLink) {
                        statusText = elText;
                        return false; // break each loop
                      }
                    }
                  });
                  
                  if (statusText) break; // Found valid status, stop checking selectors
                }
              }
            }
            
            // If no status found in the container, try fetching directly from the match page
            if (!statusText) {
              // Check if we have match ID in the URL to potentially fetch more details
              const matchId = href.match(/\/(\d+)\//);
              if (matchId && matchId[1]) {
                console.log(`No status found in homepage for match ID ${matchId[1]}, will fetch from match page if needed`);
                // We'll let the detailed view handle this when the match is selected
              }
            }
            
            // Extract winning information if this is a completed match
            let winnerInfo = '';
            const resultElement = matchContainer.find('.cb-text-complete');
            if (resultElement.length && resultElement.text().includes('won')) {
              // Extract match result with team and margin
              const resultText = resultElement.text().trim();
              
              // Validate this result belongs to THIS match
              // Check if result mentions at least one of the teams from the title
              const resultMentionsTeam = team1 && resultText.includes(team1) || 
                                        team2 && resultText.includes(team2);
              
              if (resultMentionsTeam) {
                const wonMatch = resultText.match(/(.+?)\s+won\s+by\s+(.+)/i);
                if (wonMatch) {
                  const winningTeam = shortenTeamNames(wonMatch[1].trim());
                  const margin = wonMatch[2].trim();
                  winnerInfo = `${winningTeam} won by ${margin}`;
                } else {
                  winnerInfo = resultText;
                }
              }
            }
            
            // Combine status and winner information, being careful not to duplicate
            if (statusText && winnerInfo) {
              // Don't repeat winner info if it's already in the status
              if (!statusText.includes('won')) {
                score = `${statusText} • ${winnerInfo}`;
              } else {
                score = statusText;
              }
            } else if (statusText) {
              score = statusText;
            } else if (winnerInfo) {
              score = winnerInfo;
            }
          }

          // If still no score, try to extract meaningful info from the match title or URL
          if (!score || score === 'N/A') {
            // Check title for match stage information
            if (originalTitle.includes('Preview')) {
              score = 'Match Preview';
            } else if (originalTitle.includes('Report')) {
              score = 'Match Report';
            } else {
              // Pull team information from title as fallback
              const teams = shortenTeamNames(originalTitle).split(' vs ');
              if (teams.length === 2) {
                const matchTypeHint = href.includes('test') ? 'Test' : 
                                     href.includes('odi') ? 'ODI' : 
                                     href.includes('t20') ? 'T20' : '';
                score = `${teams[0]} v ${teams[1]}${matchTypeHint ? ` (${matchTypeHint})` : ''}`;
              } else {
                score = 'Match scheduled';
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

    // If we couldn't find any matches with the primary selector,
    // try more specific selectors from older versions
    if (liveMatchesData.length === 0) {
      console.log("No matches found with primary selector, trying alternatives");
      
      const altSelectors = [
        "ul.cb-col.cb-col-100.videos-carousal-wrapper.cb-mtch-crd-rt-itm",
        "div.cb-mtch-crd-rt-itm",
        "li[class*='cb-view-all-ga cb-match-card cb-bg-white']",
        ".cb-schdl",
        ".cb-hmscg-bwtch-lst"
      ];
      
      for (const selector of altSelectors) {
        const elements = $(selector);
        console.log(`Trying selector ${selector}, found ${elements.length} elements`);
        
        if (elements.length > 0) {
          elements.each((_, el) => {
            if (matchCount >= MAX_MATCHES_MENU) return false;
            
            $(el).find('a[href*="/live-cricket-scores/"]').each((_, link) => {
              if (matchCount >= MAX_MATCHES_MENU) return false;
              
              try {
                const href = $(link).attr('href');
                const title = $(link).attr('title') || $(link).text().trim();
                
                if (href && title) {
                  const url = 'https://www.cricbuzz.com' + href;
                  
                  // Check for duplicate
                  const isDuplicate = liveMatchesData.some(match => match.url === url);
                  if (isDuplicate) return;
                  
                  let score = '';
                  const scoreElement = $(link).closest('div').find('.cb-lv-scrs-col, [class*="text-live"], [class*="text-complete"]');
                  if (scoreElement.length) {
                    score = scoreElement.text().trim();
                  }
                  
                  // Check if this is a completed match status - same logic as above
                  const thisMatchContainer = $(link).closest('li, .cb-mtch-blk, .cb-mtch-itm, .cb-srs-mtchs-tm');
                  
                  // Try to find any status text
                  const statusSelectors = [
                    '.cb-text-complete',
                    '.cb-text-live',
                    '.cb-text-preview',
                    '.cb-text-rain', 
                    '.cb-text-innings-break',
                    '.cb-text-stump',
                    '.cb-min-stts',
                    '[class*="cb-text-"]'
                  ];
                  
                  let statusText = '';
                  
                  // Check for any status text within this match's container
                  for (const selector of statusSelectors) {
                    const statusEl = thisMatchContainer.find(selector);
                    if (statusEl.length) {
                      statusText = statusEl.text().trim();
                      if (statusText) break;
                    }
                  }
                  
                  if (statusText) {
                    score = statusText;
                  } else if (score === '') {
                    // Check title for match stage information
                    if (title.includes('Preview')) {
                      score = 'Match Preview';
                    } else if (title.includes('Report')) {
                      score = 'Match Report';
                    } else {
                      // Look for other meaningful info like date or time
                      const dateElement = $(link).closest('div').find('div.cb-font-12');
                      if (dateElement && dateElement.length) {
                        score = dateElement.text().trim();
                      } else {
                        // Just extract teams as fallback
                        const teams = shortenTeamNames(title).split(' vs ');
                        if (teams.length === 2) {
                          score = `${teams[0]} v ${teams[1]}`;
                        } else {
                          score = 'Match scheduled';
                        }
                      }
                    }
                  }
                  
                  const shortTitle = shortenTeamNames(title);
                  
                  liveMatchesData.push({
                    title: shortTitle.substring(0, 100),
                    score: score.substring(0, 100),
                    url: url
                  });
                  
                  matchCount++;
                  console.log(`Added match from alt selector: ${shortTitle}`);
                }
              } catch (err) {
                console.error(`Error processing match in alternate selector:`, err);
              }
            });
          });
          
          if (liveMatchesData.length > 0) {
            break; // Exit the loop if we found matches
          }
        }
      }
    }

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

  // Get previous state for this match
  const prevState = previousSelectedMatchState[url] || {};
  const prevEvent = previousEventByUrl[url] || null;
  const processedCommentaries = processedCommentaryByUrl[url] || new Set();

  const headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': CRICBUZZ_URL
  };

  try {
    console.log(`Attempting to fetch detailed score from: ${url}`);
    const response = await axios.get(url, { headers, timeout: 15000 });
    const $ = cheerio.load(response.data);

    // Initialize result object with lastEvent
    const result = {
      title: 'N/A',
      score: 'N/A',
      opponent_score: null,
      status: '',
      crr: null,
      rrr: null,
      latestCommentary: null,
      batters: [],
      bowlers: [],
      team1_name: null,
      team2_name: null,
      pom: null,
      is_complete: false,
      recent_balls: null,
      lastEvent: null, // Initialize lastEvent
      deliveryIdentifier: null // Initialize deliveryIdentifier
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
    
    let finalStatusText = '';
    let statusFound = false;
    console.log('[StatusDebug] Starting status extraction...');

    // Priority 1: Highly specific, clean statuses from dedicated elements
    const specificStatusMappings = [
      { selector: 'div.cb-text-inningsbreak', text: 'Innings Break' },
      { selector: 'div.cb-text-stumps', text: 'Stumps' },
      { selector: 'div.cb-text-lunch', text: 'Lunch Break' },
      { selector: 'div.cb-text-tea', text: 'Tea Break' },
      { selector: 'div.cb-text-drinks', text: 'Drinks Break' },
      { selector: 'div.cb-text-delayed', text: 'Match Delayed' },
      { selector: 'div.cb-text-abandoned', text: 'Match Abandoned' },
      { selector: 'div.cb-text-rain', textContains: 'Rain', defaultText: 'Rain Delay' },
      { selector: 'div.cb-text-strategic-timeout', text: 'Strategic Timeout' }
    ];

    for (const mapping of specificStatusMappings) {
      const el = $(mapping.selector).first();
      if (el.length) {
        console.log(`[StatusDebug] Priority 1: Found element with selector: ${mapping.selector}`);
        if (mapping.text) {
          finalStatusText = mapping.text;
          console.log(`[StatusDebug] Priority 1: Using predefined text: "${finalStatusText}"`);
        } else if (mapping.textContains) {
          const elText = el.text().trim();
          if (elText.toLowerCase().includes(mapping.textContains.toLowerCase())) {
            finalStatusText = elText.length > 0 && elText.length < 35 ? elText : mapping.defaultText;
            console.log(`[StatusDebug] Priority 1: Using text from element (contains ${mapping.textContains}): "${finalStatusText}"`);
          }
        }
        if (finalStatusText) {
          statusFound = true;
          break; 
        }
      }
    }

    // Priority 2: Match completed status (often has winner info)
    if (!statusFound) {
      console.log('[StatusDebug] Checking Priority 2: Match completed status...');
      const completeEl = $('div.cb-text-complete').first();
      if (completeEl.length) {
        const completeText = completeEl.text().trim();
        console.log(`[StatusDebug] Priority 2: Found .cb-text-complete, text: "${completeText}"`);
        if (completeText.includes('won by') || 
            completeText.toLowerCase().includes('match tied') || 
            completeText.toLowerCase().includes('match drawn') || 
            completeText.toLowerCase().includes('no result')) {
          finalStatusText = completeText;
          statusFound = true;
          console.log(`[StatusDebug] Priority 2: Using completion text: "${finalStatusText}"`);
        }
      }
    }
    
    // Priority 3: Check for key phrases within general status areas if not found yet
    if (!statusFound) {
        console.log('[StatusDebug] Checking Priority 3: Key phrases in general areas...');
        const generalStatusAreas = $('div.cb-min-stts, div.cb-text-inprogress, div.cb-text-live');
        const keyPhrases = [
            { phrase: "Innings Break", result: "Innings Break" },
            { phrase: "Strategic Timeout", result: "Strategic Timeout" },
            { phrase: "Stumps", result: "Stumps" },
            { phrase: "Lunch", result: "Lunch Break" },
            { phrase: "Tea", result: "Tea Break" },
            { phrase: "Drinks", result: "Drinks Break" },
            { phrase: "Rain", result: "Rain Delay" }
        ];
        
        generalStatusAreas.each((i, area) => {
            const areaText = $(area).text();
            console.log(`[StatusDebug] Priority 3: Checking area ${i} text: "${areaText.substring(0, 100)}"...`);
            for (const item of keyPhrases) {
                if (areaText.toLowerCase().includes(item.phrase.toLowerCase())) {
                    finalStatusText = item.result;
                    statusFound = true;
                    console.log(`[StatusDebug] Priority 3: Found key phrase "${item.phrase}", using: "${finalStatusText}"`);
                    return false; // Break .each loop
                }
            }
            if (statusFound) return false; // Break from generalStatusAreas.each if found
        });
    }

    // NEW Priority 4: Check for detailed chase/target status
    if (!statusFound) {
      console.log('[StatusDebug] Checking NEW Priority 4: Detailed chase/target status...');
      const chaseStatusAreas = $('div.cb-text-live, div.cb-text-inprogress, div.cb-min-stts');
      let potentialChaseStatus = '';

      chaseStatusAreas.each((i, area) => {
          const areaText = $(area).text().trim();
          console.log(`[StatusDebug] NEW Priority 4: Checking area ${i} text: "${areaText.substring(0, 150)}"...`);

          // Look for common patterns indicating a chase or target
          const chasePatterns = [
              /(.*?)\s+(?:need|require|needs|requires)\s+(\d+)\s+runs?\s+from\s+(\d+)\s+balls?/i, // Team needs X runs from Y balls
              /(.*?)\s+(?:need|require|needs|requires)\s+(\d+)\s+runs?\s+to win/i, // Team needs X runs to win
              /Target:\s*(\d+)/i, // Target: XXX
              /(.*?)\s+to win is\s+(\d+)/i, // ...to win is XXX
              /(.*?)\s+(?:trail|lead)\s+by\s+(\d+)\s+runs?/i // Team trail/lead by X runs (for multi-day)
          ];

          for (const pattern of chasePatterns) {
              const match = areaText.match(pattern);
              if (match) {
                  // Found a relevant chase pattern
                  potentialChaseStatus = match[0].trim(); // Use the full matched string

                  // Optional: Clean up leading/trailing non-essential text around the match
                  // This might need refinement based on more examples.
                  // For now, let's just use the raw match and trust the patterns are specific.

                  console.log(`[StatusDebug] NEW Priority 4: Found chase pattern match: "${potentialChaseStatus}"`);

                  // Validate the extracted status - ensure it's not just junk or too long
                  if (potentialChaseStatus.length > 0 && potentialChaseStatus.length < 80) { // Limit length
                      // Check if it contains at least one number (runs or balls)
                      if (/\d/.test(potentialChaseStatus)) {
                           finalStatusText = potentialChaseStatus;
                           statusFound = true;
                           console.log(`[StatusDebug] NEW Priority 4: Using extracted chase status: "${finalStatusText}"`);
                           return false; // Break .each loop once found
                      }
                  }
                   console.log('[StatusDebug] NEW Priority 4: Pattern matched, but validation failed. Continuing search.');
              }
          }
           if (statusFound) return false; // Break from chaseStatusAreas.each if found
      });
    }

    // Original Priority 4 (now NEW Priority 5): More generic live/in-progress status
    if (!statusFound) {
      console.log('[StatusDebug] Checking NEW Priority 5: Generic live/in-progress...');
      const liveEl = $('div.cb-text-live, div.cb-text-inprogress').first();
      if (liveEl.length) {
        let liveText = liveEl.text().trim();
        console.log(`[StatusDebug] Priority 5: Found live/inprogress element, text: "${liveText}"`);
        
        // First, check if the text contains runs/balls requirements - KEEP this text as is
        if (liveText.match(/need|require|needs|requires|to win|target|runs?|balls?|overs?/i) && /\d+/.test(liveText)) {
          finalStatusText = liveText;
          statusFound = true;
          console.log(`[StatusDebug] Priority 5: Using detailed run chase text: "${finalStatusText}"`);
        }
        // If not a run chase but still reasonable length text, use it
        else if (liveText.length > 0 && liveText.length < 30) { 
          finalStatusText = liveText;
          statusFound = true;
          console.log(`[StatusDebug] Priority 5: Using short status text: "${finalStatusText}"`);
        } 
        // Otherwise fallback to generic status
        else if (liveText.length > 0) { 
          finalStatusText = liveText.toLowerCase().includes("live") ? "Live" : "In Progress";
          statusFound = true;
          console.log(`[StatusDebug] Priority 5: Using generic status: "${finalStatusText}"`);
        }
      }
    }
    
    // Original Priority 5 (now NEW Priority 6): Last resort - the cb-min-stts element, but heavily cleaned.
    if (!statusFound) {
        console.log('[StatusDebug] Checking NEW Priority 6: Fallback to cb-min-stts with cleaning...');
        const minSttsEl = $('div.cb-min-stts').first();
        if (minSttsEl.length) {
            let fullText = minSttsEl.text().trim();
            console.log(`[StatusDebug] Priority 6: Full text from cb-min-stts: "${fullText.substring(0,150)}"`);
            let cleanedStatus = fullText;

            const knownKeyPhrasesInFullText = ["Innings Break", "Strategic Timeout", "Stumps", "Lunch", "Tea", "Drinks Break", "Rain Delay", "Match Delayed", "Match Abandoned"];
            let extractedPhrase = "";
            for (const phrase of knownKeyPhrasesInFullText) {
                if (fullText.toLowerCase().includes(phrase.toLowerCase())) {
                    extractedPhrase = phrase;
                    console.log(`[StatusDebug] Priority 6: Extracted key phrase "${extractedPhrase}" from cb-min-stts.`);
                    break;
                }
            }

            if (extractedPhrase) {
                cleanedStatus = extractedPhrase;
            } else {
                // If no specific phrase, then aggressively clean the whole string
                const delimiters = [
                  "CRR:", "RRR:", "Commentary:", "Recent:", "Last Wkt:", 
                  "Partnership:", "Toss:", "All Series", "Move to top", 
                  "Key Stats", "Last 5 overs", "wicketkeeper", "bowler",
                  "fielder", "batting", "bowling",
                  "run out", "lbw", "caught", "bowled", "stumped",
                  "target", "trail by", "lead by", "elected to", "opt to",
                  "need", "runs", "wickets", "from", "balls", "overs",
                  "Today", "Tomorrow", "Yesterday",
                  "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
                  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
                ];

                // First, remove text after primary delimiters that often precede junk
                const primaryJunkDelimiters = ["CRR:", "RRR:", "Commentary:", "Recent:", "Last Wkt:", "Key Stats", "All Series", "Partnership:", "Last 5 overs", "Toss:"];
                for (const delimiter of primaryJunkDelimiters) {
                    if (cleanedStatus.includes(delimiter)) {
                        cleanedStatus = cleanedStatus.substring(0, cleanedStatus.indexOf(delimiter)).trim();
                    }
                }
                
                // Remove common cricbuzz patterns and extra info
                cleanedStatus = cleanedStatus.replace(/-\s*{{premiumScreenName}}\s*-/gi, '').trim();
                cleanedStatus = cleanedStatus.replace(/-\s*\w+\s*-\s*\w+(\s+\w+)*\s*-\s*Click for more details/gi, '').trim();
                cleanedStatus = cleanedStatus.replace(/Click here for full scorecard.*/gi, '').trim();
                cleanedStatus = cleanedStatus.replace(/View Full Commentary.*/gi, '').trim();
                
                // Attempt to remove player names if they are structured like " - Player Name - "
                // This is tricky and might need refinement.
                // cleanedStatus = cleanedStatus.replace(/-\s+([A-Z][a-z]+(\s+[A-Z][a-z]+)+)\s+-/g, '').trim();


                // Remove any leading non-alphanumeric characters (except spaces) like '» - '
                cleanedStatus = cleanedStatus.replace(/^[^a-zA-Z0-9\s]+/, '').trim();
                // Remove trailing non-alphanumeric characters
                cleanedStatus = cleanedStatus.replace(/[^a-zA-Z0-9\s]+$/, '').trim();

                // If it's too long after cleaning, or doesn't look like a status, it's suspect
                // Also add a check if it contains a relevant status keyword even if short
                const relevantStatusKeywords = ["Innings Break", "Stumps", "Lunch", "Tea", "Drinks Break", "Rain Delay", "Match Delayed", "Abandoned"];
                const isLikelyStatus = cleanedStatus.length > 0 && cleanedStatus.length < 50 && // Increased length slightly
                                       (!cleanedStatus.match(/(\d+\/d+)|(\d+s*ov)/) || // Avoid scores unless part of a chase status
                                        relevantStatusKeywords.some(keyword => cleanedStatus.includes(keyword)) || // Explicitly allow known states
                                        cleanedStatus.toLowerCase().includes('target') || // Explicitly allow target
                                        cleanedStatus.toLowerCase().includes('win') || // Explicitly allow 'win'
                                        cleanedStatus.toLowerCase().includes('lead') || // Explicitly allow 'lead'
                                        cleanedStatus.toLowerCase().includes('trail')); // Explicitly allow 'trail'


                if (isLikelyStatus) {
                    finalStatusText = cleanedStatus;
                    statusFound = true;
                    console.log(`[StatusDebug] NEW Priority 6: Using cleaned status: "${finalStatusText}"`);
                } else if (cleanedStatus.length === 0 && fullText.toLowerCase().includes("live")){
                    finalStatusText = "Live"; // if cleaning removed everything but it was live
                    statusFound = true;
                     console.log(`[StatusDebug] NEW Priority 6: Fallback to Live after cleaning.`);
                } else {
                    console.log(`[StatusDebug] NEW Priority 6: Cleaned status "${cleanedStatus}" did not pass validation.`);
                }
            }
             if (extractedPhrase && !finalStatusText) { // If we got an extracted phrase but didn't set finalStatusText
                finalStatusText = extractedPhrase;
          statusFound = true;
           console.log(`[StatusDebug] NEW Priority 6: Using extracted phrase: "${finalStatusText}"`);
        }
      }
    }

    result.status = (statusFound && finalStatusText && finalStatusText.trim() !== '') ? finalStatusText.trim() : 'Match In Progress';
    console.log(`[StatusDebug] FINAL STATUS: "${result.status}" (statusFound: ${statusFound}, finalStatusText: "${finalStatusText}")`);

    // Analyze if match is complete (based on the refined status)
    result.is_complete = false; // Reset
    if (result.status) {
      const lowerStatus = result.status.toLowerCase();
      const completionIndicators = ['won by', 'match tied', 'match drawn', 'no result', 'abandoned', 'match complete'];
      result.is_complete = completionIndicators.some(indicator => lowerStatus.includes(indicator));
      if (lowerStatus.includes("innings break") || lowerStatus.includes("live") || lowerStatus.includes("in progress") || lowerStatus.includes("stumps") || lowerStatus.includes("strategic timeout") || lowerStatus.includes("drinks") || lowerStatus.includes("tea") || lowerStatus.includes("lunch") || lowerStatus.includes("delay")) {
        result.is_complete = false; // Explicitly not complete for these states
      }
    }
    console.log(`[StatusDebug] Is match complete: ${result.is_complete} (based on status: "${result.status}")`);

    // Check specific status patterns based on team names to avoid mixing up status
    // This check might be less critical now with better status parsing, but can remain as a safeguard
    if (result.is_complete && result.team1_name && result.team2_name) {
      // ... (existing validation logic for completed match status, can be kept or simplified)
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

    // --- ADDED: Extract CRR ---
    const crrElement = $('.cb-min-bat-rw .cb-font-12.cb-text-gray:contains("CRR:") span').last();
    if (crrElement.length > 0) {
      result.crr = crrElement.text().trim();
      console.log(`Found CRR: ${result.crr}`);
    }

    // --- ADDED: Extract RRR ---
    const rrrElement = $('.cb-min-bat-rw .cb-font-12.cb-text-gray:contains("REQ:") span').last(); // Cricbuzz uses REQ for Required Rate
    if (rrrElement.length > 0) {
      result.rrr = rrrElement.text().trim();
      console.log(`Found RRR: ${result.rrr}`);
    }
    // --- END ADDED ---

    // After parsing the current score, detect wicket
    const currentWicketCount = extractWicketCount(result.score);
    const previousWicketCount = prevState.wicketCount;

    if (previousWicketCount !== null && currentWicketCount !== null && 
        currentWicketCount > previousWicketCount && !result.is_complete) {
      if (canTriggerNewEvent(url, 'wicket')) {
        result.lastEvent = 'wicket';
        console.log(`[EventDebug] Wicket detected from score change: ${previousWicketCount} -> ${currentWicketCount}`);
      }
    }

    // Update commentary parsing to include event detection
    const commentaryLines = $('p.cb-com-ln.cb-col.cb-col-90');
    if (commentaryLines.length > 0) {
      const overNumberElement = $(commentaryLines[0]).closest('div').find('.cb-ovr-num');
      const overNumber = overNumberElement.length > 0 ? overNumberElement.text().trim() : '';
      result.deliveryIdentifier = overNumber; // Store the overNumber as deliveryIdentifier

      let latestCommTextRaw = $(commentaryLines[0]).text().trim();
      console.log(`[EventDebug] Raw commentary line 0: "${latestCommTextRaw}"`);
      
      let firstCommaIndex = latestCommTextRaw.indexOf(',');
      let secondCommaIndex = -1;
      if (firstCommaIndex !== -1) {
        secondCommaIndex = latestCommTextRaw.indexOf(',', firstCommaIndex + 1);
      }

      const commentaryTextForEvent = secondCommaIndex !== -1 
        ? latestCommTextRaw.substring(0, secondCommaIndex).trim()
        : latestCommTextRaw;
      
      console.log(`[EventDebug] Text for event detection (commentaryTextForEvent): "${commentaryTextForEvent}"`);
      
      // Create a unique key for this delivery by combining over number and delivery text
      const uniqueDeliveryKey = `${overNumber}-${commentaryTextForEvent}`;
      
      result.latestCommentary = `${overNumber ? overNumber + ' ' : ''}${commentaryTextForEvent}`;

      // Check if we've already processed this exact commentary
      const isCommentaryProcessed = processedCommentaries.has(uniqueDeliveryKey);
      
      // If no wicket detected yet from score, check commentary for events
      if (!result.lastEvent && !isCommentaryProcessed) {
        const eventFromComm = detectEventFromCommentary(commentaryTextForEvent);
        if (eventFromComm && canTriggerNewEvent(url, eventFromComm)) {
          result.lastEvent = eventFromComm;
          console.log(`[EventDebug] New event detected from commentary: ${eventFromComm} for delivery: ${uniqueDeliveryKey}`);
          processedCommentaries.add(uniqueDeliveryKey); // Add to processed set
        }
      } else if (isCommentaryProcessed && !result.lastEvent) {
        console.log(`[EventDebug] Skipping duplicate delivery: ${uniqueDeliveryKey}`);
      }
    } else {
      console.log('[EventDebug] No commentary lines found with selector.');
    }

    // Store processed commentaries
    processedCommentaryByUrl[url] = processedCommentaries;
    
    // Store current state for next comparison
    if (currentWicketCount !== null) { // Only update if currentWicketCount is valid
      previousSelectedMatchState[url] = {
        wicketCount: currentWicketCount,
        score: result.score,
        latestCommentary: result.latestCommentary,
        deliveryIdentifier: result.deliveryIdentifier // Also store deliveryIdentifier in state
      };
    }
    
    // Store the current event for next comparisons
    if (result.lastEvent) {
      previousEventByUrl[url] = result.lastEvent;
    }

    console.log(`[EventDebug] Final event for this update: ${result.lastEvent || 'none'}`);

    // Update Tray Tooltip Logic (include CRR/RRR)
    let displayValue = null;
    if (result.is_complete && result.status && result.status !== 'N/A') {
      displayValue = result.status;
    } else if (result.score && result.score !== 'N/A') {
      displayValue = `${result.score}${result.crr ? ' CRR:' + result.crr : ''}${result.rrr ? ' RRR:' + result.rrr : ''}`;
      // Append status if it provides additional info (like 'Innings Break')
      if (result.status && result.status !== 'N/A' && !result.status.toLowerCase().includes('live')) {
           displayValue += ` | ${result.status}`;
      }
    }
    selectedMatchLiveScore = displayValue;
    updateTrayTooltip(selectedMatchLiveScore); // Update tooltip only

    console.log('Successfully parsed detailed score data (with CRR/RRR if available)');
    // console.log(JSON.stringify(result, null, 2)); // Optional: Log the full result for debugging
    return result;

  } catch (error) {
    console.error('Error fetching detailed score:', error);
    // Ensure state isn't updated with stale data on error
    selectedMatchLiveScore = null;
    updateTrayTooltip(null);
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

ipcMain.handle('fetch-detailed-score', async (_event, url) => {
  console.log(`IPC Invoked: fetch-detailed-score for ${url} (Initial Fetch)`);
  currentMatchUrl = url;

  const details = await fetchDetailedScore(url);

  if (details) {
    // Cache the true state from the fetch, including any event found.
    // This is important for the subsequent periodic updates to compare against.
    previousSelectedMatchState[url] = { ...details };
    
    // For the *initial* data sent back to the renderer via invoke,
    // explicitly nullify event fields to prevent animation on first load.
    const initialDetailsForRenderer = { ...details, lastEvent: null, deliveryIdentifier: null };
    console.log(`[IPC Initial Fetch] Returning details for ${url} with lastEvent nullified for renderer.`);
    return initialDetailsForRenderer;
  }
  console.log(`[IPC Initial Fetch] No details found for ${url}.`);
  return null;
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

// --- ADDED: Window Resize Handler ---
ipcMain.on('resize-window', (_, isMinimized) => {
  if (mainWindow && !mainWindow.isDestroyed()) {
    console.log(`Resizing window for minimized: ${isMinimized}`);
    
    // Get current position and bounds
    const bounds = mainWindow.getBounds();
    
    // Set new height based on minimized state
    const newHeight = isMinimized ? WINDOW_HEIGHT_MINIMIZED : WINDOW_HEIGHT;
    
    // Keep the same X position and width, but update the height
    // Also adjust Y position to maintain the bottom anchoring
    mainWindow.setBounds({
      x: bounds.x,
      y: bounds.y + (bounds.height - newHeight), // Move down by the difference to keep bottom edge in same place
      width: bounds.width,
      height: newHeight
    }, true); // true for animated transition
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

  // Set background to fully transparent for both dev and prod
  const bgColor = '#00000000';

  mainWindow = new BrowserWindow({
    width: windowWidth,
    height: windowHeight,
    show: false,
    frame: false,
    titleBarStyle: 'hidden',
    fullscreenable: false,
    resizable: false,
    movable: true,
    transparent: true, // Enable transparency for both dev and prod
    backgroundColor: bgColor,
    opacity: 1.0,
    roundedCorners: true,
    hasShadow: true,
    thickFrame: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    webPreferences: {
      preload: join(__dirname, 'preload.mjs'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false, // Required for ESM preload scripts
      webSecurity: !isDev,
      defaultFontFamily: {
        standard: '-apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Oxygen, Ubuntu, Cantarell, Open Sans, Helvetica Neue, sans-serif',
      },
      defaultBackgroundColor: bgColor,
      experimentalFeatures: true,
      devTools: true
    }
  });

  // Set background color to match
  mainWindow.setBackgroundColor(bgColor);

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
    const prodPath = join(__dirname, '../dist/index.html');
    const prodUrl = `file://${prodPath}`;
    console.log(`Loading production URL: ${prodUrl}`);
    mainWindow.loadURL(prodUrl).catch(err => {
      console.error('Failed to load production URL:', err);
    });
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
    staticIconPath = join(__dirname, '..', 'public', iconName);
  } else {
    staticIconPath = join(app.getAppPath(), 'public', iconName);
  }

  console.log(`Attempting to load static tray icon from: ${staticIconPath}`); 

  try {
    // Check if the icon file exists
    if (fs.existsSync(staticIconPath)) {
      console.log(`Tray icon file exists at: ${staticIconPath}`);
      defaultTrayIcon = nativeImage.createFromPath(staticIconPath);
      
      if (defaultTrayIcon.isEmpty()) {
        console.error('Tray icon created but is empty');
      } else {
        console.log('Tray icon loaded successfully');
        const size = defaultTrayIcon.getSize();
        console.log(`Icon size: ${size.width}x${size.height}`);
      }
    } else {
      console.error(`Tray icon file does not exist at: ${staticIconPath}`);
      // Try to see what's in the directory
      const iconDir = join(staticIconPath, '..');
      if (fs.existsSync(iconDir)) {
        console.log(`Files in icon directory (${iconDir}):`);
        const files = fs.readdirSync(iconDir);
        console.log(files);
      } else {
        console.error(`Icon directory does not exist: ${iconDir}`);
      }
      
      // Create an empty icon as fallback
      defaultTrayIcon = nativeImage.createEmpty();
      console.log('Using empty icon as fallback');
    }
  } catch (error) {
    console.error('Error loading tray icon:', error);
    defaultTrayIcon = nativeImage.createEmpty();
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
          if (mainWindow && !mainWindow.isDestroyed()) {
            if (currentMatchUrl) {
              // If a match is selected, refresh its details
              console.log(`Manual refresh triggered for selected match: ${currentMatchUrl}`);
              const details = await fetchDetailedScore(currentMatchUrl);
              if (details) {
                mainWindow.webContents.send('update-selected-details', details);
              }
            } else {
              // If on the match list, refresh the list
              console.log('Manual refresh triggered for match list.');
              await fetchAndParseCricbuzz(); 
              mainWindow.webContents.send('refresh-data');
            }
          }
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
  createWindow();
  createTray();

  // Start periodic updates for the match list (less frequent)
  setInterval(async () => {
    try {
      // Only fetch list if no match is selected AND window exists
      if (!currentMatchUrl && mainWindow && !mainWindow.isDestroyed()) { 
        console.log('Periodic refresh triggered for match list.');
        await fetchAndParseCricbuzz();
        mainWindow.webContents.send('refresh-data'); 
      }
    } catch(error) {
        console.error('Error during periodic list refresh:', error);
    }
  }, UPDATE_INTERVAL_SECONDS * 1000);

  // Start periodic updates for the SELECTED match details (more frequent)
  setInterval(async () => {
    if (mainWindow && !mainWindow.isDestroyed() && currentMatchUrl) { // Only run if window exists and a match is selected
      try {
        console.log(`Periodic refresh triggered for selected match: ${currentMatchUrl}`);
        const details = await fetchDetailedScore(currentMatchUrl);
        if (details) {
          mainWindow.webContents.send('update-selected-details', details); 
        }
      } catch (error) {
        console.error(`Error during periodic detail refresh for ${currentMatchUrl}:`, error);
      }
    }
  }, DETAILED_UPDATE_INTERVAL_SECONDS * 1000); 

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
        if (!mainWindow || mainWindow.isDestroyed()) {
          createWindow();
        } else {
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
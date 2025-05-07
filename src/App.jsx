import React, { useState, useEffect, useRef, useLayoutEffect } from 'react';
import './App.css';

function App() {
  const [matches, setMatches] = useState([]);
  const [selectedMatchData, setSelectedMatchData] = useState(null);
  const [isMinimizedView, setIsMinimizedView] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [theme, setTheme] = useState('dark'); // Default theme state
  const [commentary, setCommentary] = useState('');
  const [showCommentary, setShowCommentary] = useState(false);
  const [isPinned, setIsPinned] = useState(false);
  const [currentEvent, setCurrentEvent] = useState(null);
  const [animationKey, setAnimationKey] = useState(0); // Add animation key for forced re-render
  const [showEventOverlay, setShowEventOverlay] = useState(false);

  // Event animation timeout ref
  const eventTimeoutRef = useRef(null);
  const overlayTimeoutRef = useRef(null);
  const processedEventInstanceRef = useRef(null); // Ref to store the last processed event instance

  // --- Data Fetching ---
  const fetchData = async () => {
    setLoading(true);
    setError(null);
    console.log("Fetching initial matches...");
    try {
      const fetchedMatches = await window.electronAPI.fetchMatches();
      setMatches(fetchedMatches || []);
    } catch (err) {
      console.error("Error fetching matches:", err);
      setError('Failed to fetch match list. Please check your internet connection.');
      setMatches([]); // Clear matches on error
    } finally {
      setLoading(false);
    }
  };

  const fetchDetails = async (url) => {
    if (!url) return;
    console.log("Fetching details for:", url);
    try {
      const details = await window.electronAPI.fetchDetailedScore(url);
      setSelectedMatchData(details);
    } catch (err) {
      console.error("Error fetching details:", err);
      setError('Failed to fetch match details. Please try again.');
    }
  };

  const fetchCommentary = async () => {
    if (!selectedMatchData || !selectedMatchData.url) return;
    
    try {
      const commentaryData = await window.electronAPI.fetchCommentary(selectedMatchData.url);
      if (commentaryData && commentaryData.commentary) {
        setCommentary(commentaryData.commentary);
      } else {
        setCommentary("No commentary available at the moment");
      }
    } catch (err) {
      console.error("Error fetching commentary:", err);
      setCommentary("Failed to fetch commentary");
    }
  };

  // Force animation reset when a new event occurs
  const resetAnimation = (event) => {
    // Clear any existing animation
    if (eventTimeoutRef.current) {
      clearTimeout(eventTimeoutRef.current);
    }
    if (overlayTimeoutRef.current) {
      clearTimeout(overlayTimeoutRef.current);
    }
    
    // Force a re-render by changing the animation key
    setAnimationKey(prevKey => prevKey + 1);
    
    // Set the new event and show overlay with a slight delay
    setTimeout(() => {
      setCurrentEvent(event);
      setShowEventOverlay(true);
    }, 50); // Small delay to ensure proper sequencing
    
    // Hide overlay after animation
    overlayTimeoutRef.current = setTimeout(() => {
      setShowEventOverlay(false);
    }, 1500); // Match the CSS animation duration
    
    // Clear animation class after full duration
    eventTimeoutRef.current = setTimeout(() => {
      setCurrentEvent(null);
    }, 2000); // Slightly longer than the longest animation
  };

  // Handle match data updates with event detection
  const handleMatchDataUpdate = (details) => {
    console.log('[App.jsx] Received details in handleMatchDataUpdate:', details);
    setSelectedMatchData(details); // Update match data first

    if (details?.lastEvent) {
      let eventInstanceId = null;
      if (details.deliveryIdentifier && details.deliveryIdentifier.trim() !== '') {
        eventInstanceId = `${details.lastEvent}-${details.deliveryIdentifier}`;
      } else {
        // Fallback if deliveryIdentifier is not available
        eventInstanceId = `${details.lastEvent}-${details.latestCommentary?.substring(0, 30)}`;
      }

      console.log(`[App.jsx] Current event instance: ${eventInstanceId}, Previously processed: ${processedEventInstanceRef.current}`);

      if (eventInstanceId !== processedEventInstanceRef.current) {
        console.log(`[App.jsx] New unique event detected: ${eventInstanceId}. Triggering animation.`);
        resetAnimation(details.lastEvent);
        processedEventInstanceRef.current = eventInstanceId;
      } else {
        console.log(`[App.jsx] Duplicate event instance detected: ${eventInstanceId}. Animation suppressed.`);
      }
    } else {
      // If there's no current event, clear the processed event ref
      if (processedEventInstanceRef.current !== null) {
        console.log('[App.jsx] No active event. Clearing processedEventInstanceRef.');
        processedEventInstanceRef.current = null;
      }
    }
  };

  useEffect(() => {
    if (currentEvent) {
      console.log(`[App.jsx] currentEvent state updated, CSS class should be applied: event-${currentEvent}`);
    }
  }, [currentEvent]);

  // --- Effects ---
  useEffect(() => {
    fetchData(); // Initial fetch

    const removeRefreshListener = window.electronAPI.onRefreshData(() => {
      console.log('Refresh data signal received from main.');
      if (!selectedMatchData) {
        console.log('Refreshing list data as no match is selected.');
        fetchData();
      }
    });

    const removeToggleListener = window.electronAPI.onToggleView(() => {
      console.log('Toggle view triggered');
      setIsMinimizedView(prev => !prev);
      window.electronAPI.resizeWindow(!isMinimizedView); // Resize window when toggling view
    });

    const removeThemeListener = window.electronAPI.onSetTheme((newTheme) => {
      console.log('Theme received in renderer:', newTheme);
      setTheme(newTheme);
    });
    
    const removeDetailsUpdateListener = window.electronAPI.onUpdateSelectedDetails((details) => {
      if (details && selectedMatchData && details.url === selectedMatchData.url) {
        handleMatchDataUpdate(details);
      }
    });

    return () => {
      if (eventTimeoutRef.current) {
        clearTimeout(eventTimeoutRef.current);
      }
      if (overlayTimeoutRef.current) {
        clearTimeout(overlayTimeoutRef.current);
      }
      removeRefreshListener();
      removeToggleListener();
      removeThemeListener();
      removeDetailsUpdateListener();
    };
  }, [selectedMatchData]); // Dependency array includes selectedMatchData to re-subscribe if it changes

  useEffect(() => {
    if (showCommentary) {
      fetchCommentary();
    }
  }, [showCommentary, selectedMatchData?.url]);

  // Cleanup timeouts on unmount
  useEffect(() => {
    return () => {
      if (eventTimeoutRef.current) clearTimeout(eventTimeoutRef.current);
      if (overlayTimeoutRef.current) clearTimeout(overlayTimeoutRef.current);
    };
  }, []);

  // Get the overlay text based on the event
  const getOverlayText = (event) => {
    switch(event) {
      case 'four': return 'FOUR!';
      case 'six': return 'SIX!';
      case 'wicket': return 'WICKET!';
      default: return '';
    }
  };

  // --- Handlers ---
  const handleMatchSelect = (url) => {
    console.log("Match selected:", url);
    window.electronAPI.selectMatch(url); // Tell main process
    fetchDetails(url); // Fetch details immediately
    setShowCommentary(false);
    processedEventInstanceRef.current = null; // Reset processed event when changing matches
  };

  const toggleCommentary = () => {
    setShowCommentary(!showCommentary);
  };

  const togglePin = () => {
    console.log(`[Pin Debug] Before toggle: isPinned = ${isPinned}`);
    const newPinnedState = !isPinned;
    console.log(`[Pin Debug] Setting new pinned state to: ${newPinnedState}`);
    setIsPinned(newPinnedState);
    
    // Try to call the IPC method with a short delay to ensure state is updated
    setTimeout(() => {
      console.log(`[Pin Debug] Calling IPC setAlwaysOnTop with: ${newPinnedState}`);
      window.electronAPI.setAlwaysOnTop(newPinnedState);
    }, 10);
  };

  // --- Table Components ---
  const BattersTable = ({ batters }) => {
    if (!batters || batters.length === 0) return null;
    return (
      <div className="table-container">
        <h4>Batting</h4>
        <table className="stats-table">
          <thead>
            <tr>
              <th>Batter</th>
              <th>R</th>
              <th>B</th>
              <th>4s</th>
              <th>6s</th>
              <th>SR</th>
            </tr>
          </thead>
          <tbody>
            {batters.map((batter, index) => (
              <tr key={index}>
                <td>{batter.name}</td>
                <td>{batter.runs}</td>
                <td>{batter.balls}</td>
                <td>{batter.fours}</td>
                <td>{batter.sixes}</td>
                <td>{batter.strikeRate}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  const BowlersTable = ({ bowlers }) => {
    if (!bowlers || bowlers.length === 0) return null;
    return (
      <div className="table-container">
        <h4>Bowling</h4>
        <table className="stats-table">
          <thead>
            <tr>
              <th>Bowler</th>
              <th>O</th>
              <th>M</th>
              <th>R</th>
              <th>W</th>
              <th>Econ</th>
            </tr>
          </thead>
          <tbody>
            {bowlers.map((bowler, index) => (
              <tr key={index}>
                <td>{bowler.name}</td>
                <td>{bowler.overs}</td>
                <td>{bowler.maidens}</td>
                <td>{bowler.runs}</td>
                <td>{bowler.wickets}</td>
                <td>{bowler.economy}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  // --- Rendering ---
  if (error) {
    return (
      <div className="container error">
        <p>Error: {error}</p>
        <button onClick={fetchData}>Retry</button>
      </div>
    );
  }

  return (
    <div className={`container ${theme}`}>
      {!selectedMatchData ? (
        // Match List View
        <div className="match-list">
          <h2>Live Matches</h2>
          <ul style={{ maxHeight: 'calc(100% - 60px)', overflowY: 'auto' }}>
            {matches.length > 0 ? (
              matches.map((match) => (
                <li key={match.url} onClick={() => handleMatchSelect(match.url)}>
                  <span className="match-title">{match.title}</span>
                  <span className="match-score">{match.score}</span>
                </li>
              ))
            ) : (
              <>
              <li>No live matches found.</li>
              {/* Placeholder items... */}
              </>
            )}
          </ul>
        </div>
      ) : (
        // Detail View (minimized or full) with event overlay
        <React.Fragment>
          {/* Event Overlay */}
          {showEventOverlay && currentEvent && (
            <div key={`overlay-${animationKey}`} className={`event-overlay event-${currentEvent}-overlay`}>
              <span className="event-text">{getOverlayText(currentEvent)}</span>
            </div>
          )}
          
          {isMinimizedView ? (
        // Minimized Detail View
            <div key={`min-${animationKey}`} className={`match-detail minimized ${currentEvent ? `event-${currentEvent}` : ''}`}>
          <div className="minimized-header">
            {/* Add expand button */}
            <button 
              className="icon-button expand-button" 
              onClick={() => {
                console.log("[Resize Debug] Expanding view");
                setIsMinimizedView(false);
                window.electronAPI.resizeWindow(false); // Resize window when expanding
              }}
              title="Expand view">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 6v12m-6-6h12"></path>
              </svg>
            </button>
            
            {/* Pin/Unpin button for minimized view */}
            <button 
              className="icon-button pin-button" 
              onClick={togglePin} 
              title={isPinned ? "Unpin window" : "Pin window (Always on Top)"}
            >
              {isPinned ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="2" y1="2" x2="22" y2="22"></line>
                  <path d="M14.5 10.5c-1.31.68-2.87.5-4.05-.17l-5.58 5.58c-1.56 1.56-1.56 4.09 0 5.66.78.78 1.8 1.17 2.83 1.17s2.05-.39 2.83-1.17l5.58-5.58c.68-1.18.85-2.74.17-4.05M18 12l2-2 1-1c.63-.63.63-1.7 0-2.34l-2.34-2.34c-.63-.63-1.7-.63-2.34 0l-1 1-2 2M7.5 2.5l1 1M14 8.5c.78.78 1.17 1.8 1.17 2.83 0 .71-.14 1.4-.42 2.02"></path>
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14.5 10.5c-1.31.68-2.87.5-4.05-.17l-5.58 5.58c-1.56 1.56-1.56 4.09 0 5.66.78.78 1.8 1.17 2.83 1.17s2.05-.39 2.83-1.17l5.58-5.58c.68-1.18.85-2.74.17-4.05M18 12l2-2 1-1c.63-.63.63-1.7 0-2.34l-2.34-2.34c-.63-.63-1.7-.63-2.34 0l-1 1-2 2M7.5 2.5l1 1M14 8.5c.78.78 1.17 1.8 1.17 2.83 0 1.02-.39 2.05-1.17 2.83"></path>
                </svg>
              )}
            </button>
          </div>
          {/* Remove title, keep only score and status */}
          <p className="mini-score">{selectedMatchData.score} {selectedMatchData.opponent_score ? `| ${selectedMatchData.opponent_score}` : ''}</p>
          <p className="mini-status">{selectedMatchData.status}</p>
        </div>
      ) : (
        // Full Detail View
            <div key={`full-${animationKey}`} className={`match-detail ${currentEvent ? `event-${currentEvent}` : ''}`}>
          {/* Icon Button Group */}
          <div className="icon-button-group">
            {/* Back button (left) */}
            <button className="icon-button back-button" onClick={() => { setSelectedMatchData(null); processedEventInstanceRef.current = null; }} title="Back to list">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M15 18l-6-6 6-6" />
              </svg>
            </button>
            
            {/* Pin/Unpin button (middle) */}
            <button 
              className="icon-button pin-button" 
              onClick={togglePin} 
              title={isPinned ? "Unpin window" : "Pin window (Always on Top)"}
            >
              {isPinned ? (
                // Unpin Icon (e.g., pin with slash)
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="2" y1="2" x2="22" y2="22"></line>
                  <path d="M14.5 10.5c-1.31.68-2.87.5-4.05-.17l-5.58 5.58c-1.56 1.56-1.56 4.09 0 5.66.78.78 1.8 1.17 2.83 1.17s2.05-.39 2.83-1.17l5.58-5.58c.68-1.18.85-2.74.17-4.05M18 12l2-2 1-1c.63-.63.63-1.7 0-2.34l-2.34-2.34c-.63-.63-1.7-.63-2.34 0l-1 1-2 2M7.5 2.5l1 1M14 8.5c.78.78 1.17 1.8 1.17 2.83 0 .71-.14 1.4-.42 2.02"></path>
                </svg>
              ) : (
                // Pin Icon
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14.5 10.5c-1.31.68-2.87.5-4.05-.17l-5.58 5.58c-1.56 1.56-1.56 4.09 0 5.66.78.78 1.8 1.17 2.83 1.17s2.05-.39 2.83-1.17l5.58-5.58c.68-1.18.85-2.74.17-4.05M18 12l2-2 1-1c.63-.63.63-1.7 0-2.34l-2.34-2.34c-.63-.63-1.7-.63-2.34 0l-1 1-2 2M7.5 2.5l1 1M14 8.5c.78.78 1.17 1.8 1.17 2.83 0 1.02-.39 2.05-1.17 2.83"></path>
                </svg>
              )}
            </button>

            {/* Minimize button (right) */}
            <button className="icon-button minimize-button" onClick={() => {
              console.log("[Resize Debug] Minimizing view");
              setIsMinimizedView(true);
              window.electronAPI.resizeWindow(true); // Resize window when minimizing
            }} title="Minimize view">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>

              <div className="match-header">
          <h3>{selectedMatchData.title}</h3>
                {/* Score Line with RRR on left, Score in center, CRR on right */}
                <p className="score-line">
                  {selectedMatchData.rrr ? (
                    <span className="run-rate rrr">RRR: {selectedMatchData.rrr}</span>
                  ) : <span className="run-rate rrr">&nbsp;</span>}
                  <span className="main-score">{selectedMatchData.score}</span>
                  {selectedMatchData.crr ? (
                    <span className="run-rate crr">CRR: {selectedMatchData.crr}</span>
                  ) : <span className="run-rate crr">&nbsp;</span>}
                  {selectedMatchData.opponent_score && (
                    <div className="opponent-score">| {selectedMatchData.opponent_score}</div>
                  )}
                </p>
          <p className="status">{selectedMatchData.status}</p>
                {selectedMatchData.latestCommentary && (
                  <p className="latest-commentary">
                    {selectedMatchData.latestCommentary}
                  </p>
                )}
              </div>
          
          <BattersTable batters={selectedMatchData.batters} />
          <BowlersTable bowlers={selectedMatchData.bowlers} />
          
          {selectedMatchData.is_complete && selectedMatchData.pom && (
            <p className="pom">POM: {selectedMatchData.pom}</p>
          )}
        </div>
          )}
        </React.Fragment>
      )}
    </div>
  );
}

export default App; 
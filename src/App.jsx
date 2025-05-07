import React, { useState, useEffect, useRef } from 'react';
import './App.css';

function App() {
  const [matches, setMatches] = useState([]);
  const [selectedMatchData, setSelectedMatchData] = useState(null);
  const [isMinimizedView, setIsMinimizedView] = useState(false);
  const [loading, setLoading] = useState(true); // For initial list load, or if list is empty
  const [matchLoading, setMatchLoading] = useState(false); // For individual match load
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
  const isMatchJustSelected = useRef(false); // Ref to track if a match was just selected

  // Ref to hold the current selectedMatchData for use in listeners
  const selectedMatchDataRef = useRef(null);
  useEffect(() => {
    selectedMatchDataRef.current = selectedMatchData;
  }, [selectedMatchData]);

  // --- Data Fetching ---
  const fetchData = async (isInitialOrForcedRefresh = false) => {
    if (isInitialOrForcedRefresh || matches.length === 0) {
      setLoading(true); // Show full loading screen only on first load or if list is empty
    }
    // For background refreshes of an existing list, setLoading(true) is skipped.
    console.log(`Fetching matches... (Initial/Forced/Empty: ${isInitialOrForcedRefresh || matches.length === 0})`);
    setError(null); // Clear previous list errors
    try {
      const fetchedMatches = await window.electronAPI.fetchMatches();
      setMatches(fetchedMatches || []);
    } catch (err) {
      console.error("Error fetching matches:", err);
      setError('Failed to fetch match list.');
      if (matches.length === 0 && !isInitialOrForcedRefresh) setMatches([]); // Ensure list is empty if fetch fails and it was empty
    } finally {
      if (isInitialOrForcedRefresh || matches.length === 0) {
         // This condition for setLoading(false) should ideally mirror when setLoading(true) was called.
         // However, matches.length might have changed due to setMatches above.
         // So, more robustly, we use the flag or if loading was true.
         if (loading || isInitialOrForcedRefresh) setLoading(false);
      }
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
    const currentMatch = selectedMatchDataRef.current;
    if (!currentMatch || !currentMatch.url) return;
    try {
      const commentaryData = await window.electronAPI.fetchCommentary(currentMatch.url);
      setCommentary(commentaryData?.commentary || "No commentary available");
    } catch (err) {
      console.error("Error fetching commentary:", err);
      setCommentary("Failed to fetch commentary");
    }
  };

  // Force animation reset when a new event occurs
  const resetAnimation = (event) => {
    if (eventTimeoutRef.current) clearTimeout(eventTimeoutRef.current);
    if (overlayTimeoutRef.current) clearTimeout(overlayTimeoutRef.current);
    setAnimationKey(prevKey => prevKey + 1);
    setTimeout(() => { setCurrentEvent(event); setShowEventOverlay(true); }, 50);
    overlayTimeoutRef.current = setTimeout(() => setShowEventOverlay(false), 1500);
    eventTimeoutRef.current = setTimeout(() => setCurrentEvent(null), 2000);
  };

  // Handle match data updates with event detection
  const handleMatchDataUpdate = (details) => {
    console.log('[App.jsx] Received details in handleMatchDataUpdate:', details);
    setSelectedMatchData(details);
    if (details?.lastEvent) {
      const eventInstanceId = `${details.lastEvent}-${details.deliveryIdentifier || details.latestCommentary?.substring(0, 30)}`;
      console.log(`[App.jsx] Event check: ID='${eventInstanceId}', PrevProcessed='${processedEventInstanceRef.current}', isMatchJustSelected='${isMatchJustSelected.current}'`);
      if (isMatchJustSelected.current) {
        console.log(`[App.jsx] First event-bearing update. Storing ID, suppressing animation: ${eventInstanceId}`);
        processedEventInstanceRef.current = eventInstanceId;
        isMatchJustSelected.current = false;
      } else if (eventInstanceId !== processedEventInstanceRef.current) {
        console.log(`[App.jsx] New unique event: ${eventInstanceId}. Triggering animation.`);
        resetAnimation(details.lastEvent);
        processedEventInstanceRef.current = eventInstanceId;
      } else {
        console.log(`[App.jsx] Duplicate event: ${eventInstanceId}. Animation suppressed.`);
      }
    } else {
      console.log(`[App.jsx] Update with no event. isMatchJustSelected='${isMatchJustSelected.current}'. processedEventInstanceRef='${processedEventInstanceRef.current}' (remains).`);
    }
  };

  useEffect(() => { if (currentEvent) console.log(`[App.jsx] currentEvent state updated: event-${currentEvent}`); }, [currentEvent]);

  // Main useEffect for setting up listeners and initial data fetch
  useEffect(() => {
    fetchData(true); // Initial fetch for the match list, force loading screen
    const listeners = [
      window.electronAPI.onRefreshData(() => {
        console.log('Refresh data signal received.');
        if (!selectedMatchDataRef.current) {
          console.log('Refreshing list data (no match selected).');
          fetchData(); // Not initial, will use background refresh logic
        }
      }),
      window.electronAPI.onToggleView(() => {
        console.log('Toggle view triggered');
        setIsMinimizedView(prev => { const newState = !prev; window.electronAPI.resizeWindow(newState); return newState; });
      }),
      window.electronAPI.onSetTheme(setTheme),
      window.electronAPI.onUpdateSelectedDetails((details) => {
        const currentMatch = selectedMatchDataRef.current;
        if (details && currentMatch && details.url === currentMatch.url) {
          handleMatchDataUpdate(details);
        }
      })
    ];
    return () => {
      if (eventTimeoutRef.current) clearTimeout(eventTimeoutRef.current);
      if (overlayTimeoutRef.current) clearTimeout(overlayTimeoutRef.current);
      listeners.forEach(removeListener => removeListener());
    };
  }, []);

  useEffect(() => { if (showCommentary) fetchCommentary(); }, [showCommentary]); // Depends only on showCommentary, fetchCommentary uses ref for selectedMatchData

  // Cleanup timeouts on unmount (already covered by main useEffect, but good practice if separated)
  // useEffect(() => {
  //   return () => {
  //     if (eventTimeoutRef.current) clearTimeout(eventTimeoutRef.current);
  //     if (overlayTimeoutRef.current) clearTimeout(overlayTimeoutRef.current);
  //   };
  // }, []);

  // Get the overlay text based on the event
  const getOverlayText = (event) => ({ four: 'FOUR!', six: 'SIX!', wicket: 'WICKET!' }[event] || '');

  // --- Handlers ---
  const handleMatchSelect = async (url) => {
    console.log("[App.jsx] Match selected:", url);
    isMatchJustSelected.current = true;
    processedEventInstanceRef.current = null;
    setShowCommentary(false);
    setMatchLoading(true);
    setError(null);
    window.electronAPI.selectMatch(url);
    try {
      const initialDetails = await window.electronAPI.fetchDetailedScore(url);
      if (initialDetails) {
        setSelectedMatchData(initialDetails);
        console.log("[App.jsx] Initial details set. LastEvent (should be null):", initialDetails.lastEvent);
      } else {
        setError('Failed to load match details. Try again.'); setSelectedMatchData(null);
      }
    } catch (err) {
      console.error("Error in handleMatchSelect:", err); setError('Error fetching match details.'); setSelectedMatchData(null);
    } finally {
      setMatchLoading(false);
    }
  };

  const handleBackToList = () => {
    console.log('[App.jsx] Back button clicked. Transitioning to list view.');
    window.electronAPI.selectMatch(null); // Inform main process
    setSelectedMatchData(null);         // Trigger UI change to list
    setError(null);                     // Clear any errors
    
    // Reset states specific to the detailed view
    processedEventInstanceRef.current = null;
    isMatchJustSelected.current = false; // Reset for next selection
    setCommentary('');
    setShowCommentary(false);
    setCurrentEvent(null); // Clear animation state
    if (eventTimeoutRef.current) clearTimeout(eventTimeoutRef.current);
    if (overlayTimeoutRef.current) clearTimeout(overlayTimeoutRef.current);
    setShowEventOverlay(false);
    // setMatchLoading(false); // Should already be false or not relevant here
  };

  const toggleCommentary = () => setShowCommentary(!showCommentary);

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
  if (loading) { // Initial list loading
    return <div className="container loading"><p>Loading matches...</p></div>;
  }

  if (error && !selectedMatchData && matches.length === 0) { // Show list-level error only if no match is selected and list is empty
    return (
      <div className="container error">
        <p>Error: {error}</p>
        <button onClick={() => fetchData(true)}>Retry List</button>
      </div>
    );
  }

  return (
    <div className={`container ${theme}`}>
      {!selectedMatchDataRef.current ? (
        // Match List View
        <div className="match-list">
          <h2>Live Matches</h2>
          {error && <p className="error-message">List Error: {error} (Retrying in background)</p>} {/* Show error message for list if it persists */}
          <ul style={{ maxHeight: 'calc(100% - 60px - (error ? 20px : 0px))', overflowY: 'auto' }}>
            {matches.length > 0 ? (
              matches.map((match) => (
                <li key={match.url} onClick={() => handleMatchSelect(match.url)}>
                  <span className="match-title">{match.title}</span>
                  <span className="match-score">{match.score}</span>
                </li>
              ))
            ) : (
              <li>No live matches found.</li>
            )}
          </ul>
        </div>
      ) : matchLoading ? ( // Loading state for individual match
        <div className="container loading"><p>Loading match details...</p></div>
      ) : error ? ( // Display error within the match view context if error occurred while loading specific match
         <div className="match-detail error">
            <p>Error loading match: {error}</p>
            <button onClick={handleBackToList}>Back to List</button>
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
                setIsMinimizedView(prevMinimized => {
                    window.electronAPI.resizeWindow(false); // Tell main process to expand
                    return false; // New state for isMinimizedView
                });
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
          <p className="mini-score">{selectedMatchDataRef.current.score} {selectedMatchDataRef.current.opponent_score ? `| ${selectedMatchDataRef.current.opponent_score}` : ''}</p>
          <p className="mini-status">{selectedMatchDataRef.current.status}</p>
        </div>
      ) : (
        // Full Detail View
            <div key={`full-${animationKey}`} className={`match-detail ${currentEvent ? `event-${currentEvent}` : ''}`}>
          {/* Icon Button Group */}
          <div className="icon-button-group">
            {/* Back button (left) */}
            <button className="icon-button back-button" onClick={handleBackToList} title="Back to list">
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
              setIsMinimizedView(prevMinimized => {
                  window.electronAPI.resizeWindow(true); // Tell main process to minimize
                  return true; // New state for isMinimizedView
              });
            }} title="Minimize view">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>

              <div className="match-header">
          <h3>{selectedMatchDataRef.current.title}</h3>
                {/* Score Line with RRR on left, Score in center, CRR on right */}
                <p className="score-line">
                  {selectedMatchDataRef.current.rrr ? (
                    <span className="run-rate rrr">RRR: {selectedMatchDataRef.current.rrr}</span>
                  ) : <span className="run-rate rrr">&nbsp;</span>}
                  <span className="main-score">{selectedMatchDataRef.current.score}</span>
                  {selectedMatchDataRef.current.crr ? (
                    <span className="run-rate crr">CRR: {selectedMatchDataRef.current.crr}</span>
                  ) : <span className="run-rate crr">&nbsp;</span>}
                  {selectedMatchDataRef.current.opponent_score && (
                    <div className="opponent-score">| {selectedMatchDataRef.current.opponent_score}</div>
                  )}
                </p>
          <p className="status">{selectedMatchDataRef.current.status}</p>
                {selectedMatchDataRef.current.latestCommentary && (
                  <p className="latest-commentary">
                    {selectedMatchDataRef.current.latestCommentary}
                  </p>
                )}
              </div>
          
          <BattersTable batters={selectedMatchDataRef.current?.batters} />
          <BowlersTable bowlers={selectedMatchDataRef.current?.bowlers} />
          
          {selectedMatchDataRef.current?.is_complete && selectedMatchDataRef.current?.pom && (
            <p className="pom">POM: {selectedMatchDataRef.current.pom}</p>
          )}
        </div>
          )}
        </React.Fragment>
      )}
    </div>
  );
}

export default App; 
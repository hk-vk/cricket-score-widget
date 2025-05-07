import React, { useState, useEffect, useRef } from 'react';
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
    });

    const removeThemeListener = window.electronAPI.onSetTheme((newTheme) => {
      console.log('Theme received in renderer:', newTheme);
      setTheme(newTheme);
    });
    
    const removeDetailsUpdateListener = window.electronAPI.onUpdateSelectedDetails((details) => {
      if (details && selectedMatchData && details.url === selectedMatchData.url) {
          console.log('Received updated details from main process', details);
          setSelectedMatchData(details);
      }
    });

    return () => {
      removeRefreshListener();
      removeToggleListener();
      removeThemeListener();
      removeDetailsUpdateListener();
    };
  }, [selectedMatchData]);

  useEffect(() => {
    if (showCommentary) {
      fetchCommentary();
    }
  }, [showCommentary, selectedMatchData?.url]);

  // --- Handlers ---
  const handleMatchSelect = (url) => {
    console.log("Match selected:", url);
    window.electronAPI.selectMatch(url); // Tell main process
    fetchDetails(url); // Fetch details immediately
    setShowCommentary(false);
  };

  const toggleCommentary = () => {
    setShowCommentary(!showCommentary);
  };

  const togglePin = () => {
    setIsPinned(!isPinned);
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
      ) : isMinimizedView ? (
        // Minimized Detail View
        <div className="match-detail minimized">
          <p>{selectedMatchData.title}</p>
          <p>{selectedMatchData.score} {selectedMatchData.opponent_score ? `| ${selectedMatchData.opponent_score}` : ''}</p>
          <p>{selectedMatchData.status}</p>
        </div>
      ) : (
        // Full Detail View
        <div className="match-detail">
          {/* Icon Button Group */}
          <div className="icon-button-group">
            {/* Back button (left) */}
            <button className="icon-button back-button" onClick={() => setSelectedMatchData(null)} title="Back to list">
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
                  <path d="M14.5 10.5c-1.31.68-2.87.5-4.05-.17l-5.58 5.58c-1.56 1.56-1.56 4.09 0 5.66.78.78 1.8 1.17 2.83 1.17s2.05-.39 2.83-1.17l5.58-5.58c.68-1.18.85-2.74.17-4.05"></path>
                  <path d="m18 12 2-2 1-1c.63-.63.63-1.7 0-2.34l-2.34-2.34c-.63-.63-1.7-.63-2.34 0l-1 1-2 2"></path>
                  <path d="m7.5 2.5 1 1"></path>
                  <path d="M14 8.5c.78.78 1.17 1.8 1.17 2.83 0 .71-.14 1.4-.42 2.02"></path>
                </svg>
              ) : (
                // Pin Icon
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14.5 10.5c-1.31.68-2.87.5-4.05-.17l-5.58 5.58c-1.56 1.56-1.56 4.09 0 5.66.78.78 1.8 1.17 2.83 1.17s2.05-.39 2.83-1.17l5.58-5.58c.68-1.18.85-2.74.17-4.05"></path>
                  <path d="m18 12 2-2 1-1c.63-.63.63-1.7 0-2.34l-2.34-2.34c-.63-.63-1.7-.63-2.34 0l-1 1-2 2"></path>
                  <path d="m7.5 2.5 1 1"></path>
                  <path d="M14 8.5c.78.78 1.17 1.8 1.17 2.83 0 1.02-.39 2.05-1.17 2.83"></path>
                </svg>
              )}
            </button>

            {/* Minimize button (right) */}
            <button className="icon-button minimize-button" onClick={() => setIsMinimizedView(true)} title="Minimize view">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
            </button>
          </div>

          <div className="match-header">
            <h3>{selectedMatchData.title}</h3>
            {/* Updated Score Line to include CRR/RRR */}
            <p className="score-line">
              <span className="main-score">{selectedMatchData.score}</span>
              {selectedMatchData.crr && (
                <span className="run-rate crr">&nbsp; CRR: {selectedMatchData.crr}</span>
              )}
              {selectedMatchData.rrr && (
                <span className="run-rate rrr">&nbsp; RRR: {selectedMatchData.rrr}</span>
              )}
              {selectedMatchData.opponent_score ? 
                <span className="opponent-score">&nbsp; | {selectedMatchData.opponent_score}</span> 
                : ''}
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
    </div>
  );
}

export default App; 
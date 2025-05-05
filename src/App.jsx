import React, { useState, useEffect } from 'react';
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
      console.log('Refresh triggered');
      if (selectedMatchData && selectedMatchData.url) {
        fetchDetails(selectedMatchData.url);
        if (showCommentary) {
          fetchCommentary();
        }
      } else {
        fetchData();
      }
    });

    const removeToggleListener = window.electronAPI.onToggleView(() => {
      console.log('Toggle view triggered');
      setIsMinimizedView(prev => !prev);
    });

    // Add listener for theme changes
    const removeThemeListener = window.electronAPI.onSetTheme((newTheme) => {
      console.log('Theme received in renderer:', newTheme);
      setTheme(newTheme);
    });

    // Cleanup function
    return () => {
      removeRefreshListener();
      removeToggleListener();
      removeThemeListener(); // Clean up theme listener
    };
  }, []); // Empty dependency array means run once on mount

  // Fetch commentary when showing tooltip
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
  if (loading) {
    return <div className="container loading">Loading matches...</div>;
  }

  if (error) {
    return (
      <div className="container error">
        <p>Error: {error}</p>
        <button onClick={fetchData}>Retry</button>
      </div>
    );
  }

  return (
    <div 
      className={`container ${theme}`} 
      style={{ backgroundColor: '#18181b', color: '#d1d5db' }}
    >
      {!selectedMatchData ? (
        // Match List View
        <div className="match-list" style={{ height: '280px', overflow: 'hidden' }}>
          <h2>Live Matches</h2>
          <ul style={{ height: '240px', overflowY: 'scroll', display: 'block' }}>
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
                {/* Test items - will only display when "matches" is empty  
                    This is just to test scrolling implementation */}
                <li><span className="match-title">KKR v RR - 53rd Match</span><span className="match-score">KKR won by 1 run</span></li>
                <li><span className="match-title">MI v CSK - 52nd Match</span><span className="match-score">MI: 145/6</span></li>
                <li><span className="match-title">GT v RCB - 51st Match</span><span className="match-score">RCB won by 35 runs</span></li>
                <li><span className="match-title">SRH v LSG - 50th Match</span><span className="match-score">SRH: 201/5</span></li>
                <li><span className="match-title">DC v PBKS - 49th Match</span><span className="match-score">DC won by 23 runs</span></li>
                <li><span className="match-title">CSK v RR - 48th Match</span><span className="match-score">RR: 187/5</span></li>
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
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M15 6L9 12L15 18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            
            {/* Commentary button (middle) */}
            <div className="commentary-container">
              <button 
                className="icon-button commentary-button" 
                onClick={toggleCommentary} 
                title="View commentary"
                onMouseEnter={() => setShowCommentary(true)}
                onMouseLeave={() => setShowCommentary(false)}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M19 10a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v3m-7-7a7 7 0 017-7m0 0a7 7 0 017 7m-7-7V3" 
                    stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </button>
              
              {showCommentary && (
                <div className="commentary-tooltip">
                  <div className="commentary-tooltip-content">
                    {loading ? 'Loading commentary...' : commentary || 'No commentary available'}
                  </div>
                </div>
              )}
            </div>

            {/* Minimize button (right) */}
            <button className="icon-button minimize-button" onClick={() => setIsMinimizedView(true)} title="Minimize view">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M5 12H19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          </div>

          <h3>{selectedMatchData.title}</h3>
          <p className="score">{selectedMatchData.score}</p>
          {selectedMatchData.opponent_score && <p className="opponent-score">{selectedMatchData.opponent_score}</p>}
          <p className="status">{selectedMatchData.status}</p>
          
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
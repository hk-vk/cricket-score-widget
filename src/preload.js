const { contextBridge, ipcRenderer } = require('electron');

// Expose protected methods that allow the renderer process to use
// the ipcRenderer without exposing the entire object
contextBridge.exposeInMainWorld('electronAPI', {
  // Define functions here that the renderer can call
  // Example: send: (channel, data) => ipcRenderer.send(channel, data),
  // Example: receive: (channel, func) => {
  //   ipcRenderer.on(channel, (event, ...args) => func(...args));
  // }
  // Add specific IPC channels you need
  onRefreshData: (callback) => {
    const listener = (_event) => callback();
    ipcRenderer.on('refresh-data', listener);
    // Return a function to remove the listener
    return () => {
      ipcRenderer.removeListener('refresh-data', listener);
    };
  },
  onToggleView: (callback) => {
    const listener = (_event) => callback();
    ipcRenderer.on('toggle-view', listener);
    // Return a function to remove the listener
    return () => {
      ipcRenderer.removeListener('toggle-view', listener);
    };
  },
  // Function to send match selection back to main
  selectMatch: (url) => ipcRenderer.send('select-match', url),
  // Function to fetch initial data (triggered from renderer)
  fetchMatches: () => ipcRenderer.invoke('fetch-matches'),
  fetchDetailedScore: (url) => ipcRenderer.invoke('fetch-detailed-score', url),
  // Listener for theme changes from main process
  onSetTheme: (callback) => {
    const listener = (_event, theme) => callback(theme);
    ipcRenderer.on('set-theme', listener);
    // Return cleanup function
    return () => {
      ipcRenderer.removeListener('set-theme', listener);
    };
  },
  // Listener for detail updates pushed from main process
  onUpdateSelectedDetails: (callback) => {
    const listener = (_event, details) => callback(details);
    ipcRenderer.on('update-selected-details', listener);
    return () => {
      ipcRenderer.removeListener('update-selected-details', listener);
    };
  },
});

console.log('Preload script loaded.'); 
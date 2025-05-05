import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './App.css';

console.log('src/index.jsx: Script starting'); // Log script start

const container = document.getElementById('root');

if (container) {
  console.log('src/index.jsx: Found root container, rendering App...');
  const root = createRoot(container);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
} else {
  console.error('src/index.jsx: Root container #root not found!');
} 
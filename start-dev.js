import { spawn } from 'child_process'
import http from 'http'
import { join } from 'path'
import fs from 'fs'

// Configuration
const VITE_PORT = 5173;
const MAX_RETRIES = 30;
const RETRY_DELAY = 1000; // 1 second between retries

// Colors for console output
const colors = {
  reset: '\x1b[0m',
  bright: '\x1b[1m',
  dim: '\x1b[2m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  red: '\x1b[31m',
};

// Log with colors
function log(message, color = colors.reset) {
  console.log(`${color}${message}${colors.reset}`);
}

// Start Vite development server
function startVite() {
  log('Starting Vite dev server...', colors.cyan);
  
  const viteProcess = spawn('npx', ['vite'], {
    stdio: 'pipe',
    shell: true
  });
  
  viteProcess.stdout.on('data', (data) => {
    const output = data.toString();
    // Only log important Vite messages to reduce noise
    if (output.includes('VITE') || output.includes('ready') || output.includes('error')) {
      log(`[VITE] ${output.trim()}`, colors.blue);
    }
  });
  
  viteProcess.stderr.on('data', (data) => {
    log(`[VITE ERROR] ${data}`, colors.red);
  });
  
  viteProcess.on('error', (err) => {
    log(`Failed to start Vite: ${err}`, colors.red);
    process.exit(1);
  });
  
  return viteProcess;
}

// Check if Vite server is ready
function checkViteServer(retries = 0) {
  return new Promise((resolve, reject) => {
    log(`Checking if Vite server is ready (attempt ${retries + 1}/${MAX_RETRIES})...`, colors.yellow);
    
    const req = http.get(`http://localhost:${VITE_PORT}`, (res) => {
      // Accept 200 OK or 404 Not Found as signs that the server is running
      if (res.statusCode === 200 || res.statusCode === 404) { 
        log(`✅ Vite server responded (Status: ${res.statusCode}). Assuming ready.`, colors.green);
        resolve(true);
      } else {
        log(`Vite server responded with status ${res.statusCode}`, colors.yellow);
        retry(retries, resolve, reject);
      }
    });
    
    req.on('error', (err) => {
      log(`Connection error: ${err.message}`, colors.yellow);
      retry(retries, resolve, reject);
    });
    
    req.setTimeout(1000, () => {
      req.destroy();
      log('Connection timeout', colors.yellow);
      retry(retries, resolve, reject);
    });
  });
  
  function retry(retries, resolve, reject) {
    if (retries < MAX_RETRIES - 1) {
      setTimeout(() => {
        checkViteServer(retries + 1).then(resolve).catch(reject);
      }, RETRY_DELAY);
    } else {
      log('Maximum retries reached. Vite server not responding.', colors.red);
      reject(new Error('Vite server failed to start'));
    }
  }
}

// Start Electron
function startElectron() {
  log('Starting Electron...', colors.magenta);
  
  const electronProcess = spawn('npx', ['electron', '.'], {
    stdio: 'inherit',
    shell: true
  });
  
  electronProcess.on('error', (err) => {
    log(`Failed to start Electron: ${err}`, colors.red);
  });
  
  return electronProcess;
}

// Main function
async function main() {
  try {
    log('🚀 Starting development environment...', colors.green + colors.bright);
    
    // Start Vite first
    const viteProcess = startVite();
    
    // Wait for Vite to be ready
    try {
      await checkViteServer();
      // Give a small additional delay for Vite to fully initialize
      log('Waiting 2 seconds for Vite to fully initialize...', colors.yellow);
      await new Promise(resolve => setTimeout(resolve, 2000));
      
      // Start Electron once Vite is ready
      const electronProcess = startElectron();
      
      // Handle clean shutdown
      const cleanup = () => {
        log('\nShutting down processes...', colors.yellow);
        
        electronProcess.kill();
        viteProcess.kill();
        
        setTimeout(() => {
          log('All processes terminated.', colors.green);
          process.exit(0);
        }, 1000);
      };
      
      process.on('SIGINT', cleanup);
      process.on('SIGTERM', cleanup);
      
    } catch (err) {
      log(`Error during startup: ${err.message}`, colors.red);
      viteProcess.kill();
      process.exit(1);
    }
  } catch (err) {
    log(`Startup error: ${err}`, colors.red);
    process.exit(1);
  }
}

// Run the main function
main().catch(err => {
  log(`Fatal error: ${err}`, colors.red);
  process.exit(1);
});

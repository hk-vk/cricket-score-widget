import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './', // Use relative paths for Electron build
  server: {
    port: 5173, // Default Vite port
    strictPort: true,
  },
  build: {
    outDir: 'dist', // Output directory for build
    assetsDir: '.',
    emptyOutDir: true,
  },
}); 
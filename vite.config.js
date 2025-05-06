import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig(({ command }) => ({
  plugins: [react()],
  base: command === 'serve' ? '/' : './',
  server: {
    port: 5173, // Default Vite port
    strictPort: true,
  },
  build: {
    outDir: 'dist', // Output directory for build
    emptyOutDir: true,
    cssCodeSplit: false,
  },
})); 
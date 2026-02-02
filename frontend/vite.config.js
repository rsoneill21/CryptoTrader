import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// For the proxy to work reliably, it should point to the local backend address
const apiOrigin = 'http://127.0.0.1:8000';
const wsTarget = 'ws://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  esbuild: {
    loader: 'jsx',
    include: /src\/.*\.[tj]sx?$/,
    exclude: [],
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: apiOrigin,
        changeOrigin: true,
      },
      '/auth': {
        target: apiOrigin,
        changeOrigin: true,
      },
      '/ws': {
        target: wsTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});

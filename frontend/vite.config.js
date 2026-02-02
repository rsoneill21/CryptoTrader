import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiOrigin = process.env.VITE_API_URL || 'http://localhost:8000';
const wsProtocol = apiOrigin.startsWith('https') ? 'wss' : 'ws';
const wsTarget = apiOrigin.replace(/^https?/, wsProtocol);

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

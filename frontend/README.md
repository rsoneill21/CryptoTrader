# CryptoTrader Frontend

React + TailwindCSS client powered by Vite. The frontend is responsible for rendering the dashboard, handling authentication, and streaming market data into the AI-assisted workspace.

## Requirements
- Node.js 18+ (any modern LTS work well)
- npm 10+ (bundled with Node.js 20+)

## Getting started
```bash
cd frontend
npm install
```

## Environment variables
Vite exposes `import.meta.env` variables that are prefixed with `VITE_`. The frontend honors:
- `VITE_API_URL` — overrides the backend base URL (`http://localhost:8000` when unset)

During development, the Vite dev server proxies `/api`, `/auth`, and `/ws` to `http://localhost:8000` so you can run the backend locally without CORS tweaks.

## Available scripts
```bash
npm run dev     # Start Vite dev server (http://localhost:5173)
npm run build   # Produce production assets under dist/
npm run preview # Launch a static preview of the production build
npm run lint    # Run ESLint across the React source tree
```

## Styling
TailwindCSS is already wired up via `postcss.config.js` and `tailwind.config.js`. The entry point `src/index.css` pulls in the Tailwind layers and the custom dark-theme variables used throughout the app.

## Production build
After `npm run build`, serve the `dist/` directory with your preferred static server (e.g., `npm install -g serve && serve dist`). The final bundle will call the API configured via `VITE_API_URL`, or fall back to the proxied backend when the env var is absent.

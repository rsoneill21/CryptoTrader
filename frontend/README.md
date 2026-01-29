# CryptoTrader Frontend

React + TailwindCSS storefront for the CryptoTrader experience. This project is bootstrapped with Create React App and ships with the routing, charts, and service clients that the backend expects.

## Requirements
- Node.js 18+ (the `engines` field is not locked, but modern LTS versions work best)
- npm 10+ (installed with Node.js)

## Quick start
```bash
cd frontend
npm install
```

## Environment variables
CRA automatically injects `REACT_APP_*` variables into the bundle. The frontend reads these values when building:
- `REACT_APP_API_URL` – overrides the API base URL (defaults to `http://localhost:8000`).

During local development the `proxy` field in `package.json` forwards unknown requests to `http://localhost:8000`, so you can keep CORS configuration simple.

## Scripts
```bash
npm start        # Runs the dev server (http://localhost:3000)
npm test         # Launches the Jest test runner
npm run build     # Produces a production bundle in build/
```

`npm start` runs the app with fast refresh and environment-aware logging. `npm test` loads the React Testing Library utilities already configured in `package.json`.

## TailwindCSS
Tailwind is configured in `tailwind.config.js` and consumed via the generated CSS entry in `src/index.css`. No additional build steps are required beyond `npm start` / `npm run build`.

## Production build
After running `npm run build`, serve the contents of `build/` with your preferred static file server (e.g., `serve -s build` or put the folder behind Nginx). The final bundle will call the API located at `_REACT_APP_API_URL` or the proxied backend.

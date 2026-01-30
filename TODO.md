# Outstanding Fixes

1. **ESLint warning in `frontend/src/context/AuthContext.js`:** `user_id` is assigned but never used (line 69). Clean up the unused variable or actually use it to satisfy `no-unused-vars`.
2. **Deprecated packages surfaced during `npm install`:** `rollup-plugin-terser`, `sourcemap-codec`, `stable`, `q`, Workbox modules, `whatwg-encoding`, `abab`, `domexception`, `w3c-hr-time`, `inflight`, `glob`, `rimraf`, Babel plugins, `source-map@0.8.0-beta.0`, `svgo@1.3.2`, and `eslint@8.57.1` all report deprecation warnings. Upgrade or replace them (e.g., switch to `@rollup/plugin-terser`, modern equivalents, newer ESLint) before shipping.
3. **NPM audit reported 21 vulnerabilities (15 moderate, 6 high):** run `npm audit`, apply `npm audit fix`, and re-test to ensure the fixes are safe (or document why some cannot be fixed).

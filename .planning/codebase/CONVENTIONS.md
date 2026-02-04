# Coding Conventions

**Analysis Date:** 2026-02-04

## Naming Patterns

**Files:**
- Python API routes: snake_case with descriptive names (`auth.py`, `strategies.py`, `market.py`)
- Python services: snake_case (`kraken.py`, `email.py`, `alert_service.py`)
- React components: PascalCase (`ChatWindow.js`, `PositionManager.js`, `AlertItem.js`)
- React pages: PascalCase (`AIChat.js`, `Dashboard.js`, `StrategyLab.js`)
- Utilities/services in frontend: camelCase with descriptive names (`api.js`)
- Configuration files: lowercase with dots (`vite.config.js`, `eslint.config.js`, `tailwind.config.js`)

**Functions:**
- Python: snake_case for all functions, sync and async (`get_ticker()`, `_build_technical_snapshot()`, `verify_totp()`)
- Python internal helpers: leading underscore (`_determine_log_level()`, `_format_message()`, `_kraken_error_alert()`)
- JavaScript: camelCase (`getToken()`, `setToken()`, `normalizeAPIError()`, `extractAPIError()`)
- JavaScript async: camelCase (`loadStoredChatTone()`, `ensureChatToneFetchInterceptor()`)
- React hooks: camelCase, often follow `use*` pattern if custom hooks (not yet seen but expected)

**Variables:**
- Python: snake_case (`session_token`, `order_status`, `alert_severity`)
- Python constants: UPPER_SNAKE_CASE (`VALID_EMAIL = "tester@example.com"`, `TOKEN_KEY`, `CHAT_TONE_STORAGE_KEY`)
- JavaScript: camelCase (`apiOrigin`, `wsTarget`, `backendHost`)
- JavaScript constants: UPPER_SNAKE_CASE (`DEFAULT_CHAT_TONE`, `CHAT_TONE_EVENT`, `UNEXPECTED_ERROR_MESSAGE`)

**Types:**
- Python Pydantic models: PascalCase (`RegisterRequest`, `LoginResponse`, `StrategyCreate`, `Balance`, `Ticker`, `OHLC`)
- Python Enums: PascalCase class name, UPPER_CASE values (`OrderType.MARKET`, `OrderSide.BUY`, `OrderStatus.OPEN`)
- TypeScript/JavaScript: No explicit type annotations in current codebase (untyped JavaScript)

## Code Style

**Formatting:**
- Python: No black/autopep8 formatter detected. Uses standard 4-space indentation.
- JavaScript: No Prettier formatter configured. Uses 2-space indentation in some files, varies slightly.
- Line length: Flexible, no hard limit enforced

**Linting:**
- Frontend: ESLint 9.10.0 with strict configuration
  - Config file: `frontend/eslint.config.js`
  - Plugins: `eslint-plugin-react`, `eslint-plugin-react-hooks`
  - Rules: Enforced recommended rules, disabled `react/react-in-jsx-scope`, `react/prop-types`
  - Unused vars: Allowed if prefixed with `_` (pattern: `^_`)
  - Command: `npm run lint` with `--max-warnings=0` (zero tolerance)
- Backend: No linter configuration detected in repository (relies on manual code review)

## Import Organization

**Order (Python):**
1. Standard library imports (`import asyncio`, `import logging`, `from typing import ...`)
2. Third-party imports (`from fastapi import ...`, `from pydantic import ...`, `from sqlalchemy ...`)
3. Local imports (`from core.settings import ...`, `from db.database import ...`)
4. Blank line separating groups

Example from `backend/api/auth.py`:
```python
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from core.settings import get_app_settings
from db.database import get_db
```

**Order (JavaScript):**
1. React/framework imports (`import React, { useState, ...} from 'react'`)
2. Third-party libraries (`import axios from 'axios'`)
3. Local imports and services (`import ChatWindow from '../components/ChatWindow'`, `import api from '../services/api'`)
4. Constants defined after imports

Example from `frontend/src/pages/AIChat.js`:
```javascript
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';
import ChatWindow from '../components/ChatWindow';
import api, { aiAPI } from '../services/api';

const CHAT_TONE_EVENT = 'cryptotrader:chatTonePreferenceChanged';
```

**Path Aliases:**
- Python: Relative imports from root (`from api.auth import ...`, `from db.models import ...`, `from core.settings import ...`)
- JavaScript: Relative paths with directory traversal (`import api from '../services/api'`, `import ChatWindow from '../components/ChatWindow'`)
- No alias configuration detected in either frontend or backend

## Error Handling

**Python Pattern:**
- Structured error responses via `api.errors` module
- HTTPException raised with specific status codes
- Centralized error handlers registered on FastAPI app
- Example from `backend/api/auth.py`:
  ```python
  if not user_record:
      raise HTTPException(status_code=404, detail="User not found")
  ```
- Error payload includes `code`, `message`, and optional `details`
- Log level determined by HTTP status code (4xx = warning, 5xx = error)

**JavaScript Pattern:**
- Axios interceptor pattern for response handling
- Extract error from response data (check for `data.error` object)
- Normalize errors to consistent shape: `{ message, code, details }`
- 401 errors trigger automatic logout and redirect to `/login`
- Example from `frontend/src/services/api.js`:
  ```javascript
  const normalizeAPIError = (errorResponseData) => {
    const apiError = extractAPIError(errorResponseData);
    if (!apiError) {
      return null;
    }
    return {
      message: apiError.message || apiError.detail || UNEXPECTED_ERROR_MESSAGE,
      code: apiError.code || 'unknown_error',
      details: apiError.details,
    };
  };
  ```

## Logging

**Framework:**
- Python: Standard `logging` module
- JavaScript: `console.log()`, `console.debug()` for client-side logging

**Patterns (Python):**
- Logger per module: `logger = logging.getLogger("cryptotrader.auth")` or `logger = logging.getLogger(__name__)`
- Named loggers by domain: `cryptotrader.auth`, `cryptotrader.kraken_alerts`, `cryptotrader.strategies`
- System error logging through `db.database.log_system_error()` with sanitization
- Example from `backend/api/auth.py`:
  ```python
  logger = logging.getLogger("cryptotrader.auth")
  logger.exception("Failed to process login", exc_info=True)
  ```

**Patterns (JavaScript):**
- Debug logging: `console.debug('Unable to read preferred chat tone:', error)`
- General logging: `console.log('Rendering App component')`
- No structured logging framework detected

## Comments

**When to Comment:**
- Module docstrings for files (Python uses triple-quoted strings at top)
- Function docstrings for public API functions
- Inline comments for non-obvious logic or workarounds

**JSDoc/TSDoc:**
- Python: Docstrings with triple quotes at module level
  ```python
  """
  Authentication API routes.
  """
  ```
  ```python
  """Persist a Kraken API error as an alert record."""
  ```
- JavaScript: Block comments for module documentation
  ```javascript
  /**
   * API client service for CryptoTrader.
   *
   * Provides axios instance with:
   * - Base URL configuration
   * - Auth token interceptor
   * - 401 handling (redirect to login)
   * - Error formatting
   */
  ```

## Function Design

**Size:**
- Python: Functions typically 10-50 lines, modular approach
- JavaScript: Component functions often 40-100+ lines, especially pages with multiple features

**Parameters:**
- Python: Type hints used throughout (e.g., `async def register(request: RegisterRequest, db: Session = Depends(get_db))`)
- Python FastAPI: Uses dependency injection via `Depends()` for database sessions and authentication
- JavaScript: No type annotations (untyped), parameters documented in JSDoc or clear from usage

**Return Values:**
- Python: Explicit Pydantic models for API responses (`RegisterResponse`, `LoginResponse`)
- Python async: Always return `await` or explicit Promise-like objects
- JavaScript: Returns JSX for components, plain objects for utility functions

## Module Design

**Exports (Python):**
- APIRouter instances exported as `router` from each API module
- Main services instantiated as module-level singletons (e.g., `github_import_service = GitHubImportService()`)
- Models exported from `db.models`

**Exports (JavaScript):**
- React components as default exports (`export default App`)
- Utility functions as named exports (`export const getToken = ()`, `export const setToken = ()`)
- Axios instance as default export, specific endpoints as named exports (`export const aiAPI`)

**Barrel Files:**
- Python: Not used (direct imports from modules)
- JavaScript: Not used (direct imports from components/pages)
- Example from `backend/main.py` showing direct imports:
  ```python
  from api import auth_router, market_router, system_router
  from api.alerts import router as alerts_router
  from api.ai import router as ai_router
  ```

## Async/Await Patterns

**Python:**
- FastAPI endpoints marked with `async def`
- Database operations through sync SQLAlchemy (no async driver)
- External API calls use `httpx` async client or kraken service wrappers
- Example:
  ```python
  @router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
  async def register(request: RegisterRequest, db: Session = Depends(get_db)):
  ```

**JavaScript:**
- React components use hooks: `useState`, `useEffect`, `useCallback`, `useMemo`
- Async operations with axios promises (not explicitly async/await in samples)
- Example:
  ```javascript
  const loadStoredChatTone = () => {
    if (typeof window === 'undefined') {
      return DEFAULT_CHAT_TONE;
    }
    try {
      return window.localStorage.getItem(CHAT_TONE_STORAGE_KEY) ?? DEFAULT_CHAT_TONE;
    } catch (error) {
      console.debug('Unable to read preferred chat tone:', error);
      return DEFAULT_CHAT_TONE;
    }
  };
  ```

## Validation

**Python:**
- Pydantic BaseModel for request validation (automatic via FastAPI)
- Custom validators with `@validator` decorator
- Email validation: `EmailStr` from pydantic
- Password strength validation: `validate_password_strength()` function
- Example:
  ```python
  class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
  ```

**JavaScript:**
- No explicit validation framework
- Manual checks in axios interceptors and utility functions
- Relies on backend validation with error extraction

---

*Convention analysis: 2026-02-04*

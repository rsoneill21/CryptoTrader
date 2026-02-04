# Coding Conventions

**Analysis Date:** 2026-02-04

## Naming Patterns

**Files:**
- Python backend: `snake_case.py` - e.g., `auth.py`, `database.py`, `kraken_service.py`
- JavaScript frontend: `PascalCase.js` for components (React), `camelCase.js` for utilities and hooks - e.g., `LoginForm.js`, `useAuth.js`, `api.js`

**Functions:**
- Python: `snake_case` - e.g., `hash_password()`, `verify_password()`, `validate_password_strength()`
- JavaScript: `camelCase` - e.g., `handleLogin()`, `getToken()`, `setToken()`, `clearError()`

**Variables:**
- Python: `snake_case` - e.g., `session_token`, `password_hash`, `mfa_enabled`
- JavaScript: `camelCase` - e.g., `isAuthenticated`, `setLoading`, `clearError`

**Types/Classes:**
- Python: `PascalCase` - e.g., `User`, `Session`, `RegisterRequest`, `APIErrorResponse`
- JavaScript: `PascalCase` for React components - e.g., `LoginForm`, `Layout`, `Dashboard`

**Constants:**
- Python: `UPPER_SNAKE_CASE` - e.g., `VALID_EMAIL`, `VALID_PASSWORD`, `REQUEST_ID_HEADER`
- JavaScript: `UPPER_SNAKE_CASE` - e.g., `TOKEN_KEY`, `SIDEBAR_KEY`, `UNEXPECTED_ERROR_MESSAGE`

## Code Style

**Formatting:**
- Python: No explicit formatter configured, but follows PEP 8 conventions (inferred from code style)
- JavaScript: ESLint configured in `frontend/eslint.config.js` with Prettier integration (implied by package.json dependencies)

**Linting:**
- Python: No eslint/pylint config file found - relies on natural conventions
- JavaScript: ESLint with React and React Hooks plugins configured in `frontend/eslint.config.js`
  - ES2022 as target ecmaVersion
  - Unused variable rule allows underscore prefix pattern: `argsIgnorePattern: '^_'`
  - React plugin configured with version detection
  - React Hooks recommended rules enforced

**Key JavaScript Rules:**
- `react/react-in-jsx-scope`: off (React 17+ doesn't require React import)
- `react/prop-types`: off (no prop validation required)
- `no-unused-vars`: errors if variables unused except those starting with `_`

## Import Organization

**Python Pattern:**
```python
# Standard library imports
from pathlib import Path
import os
import sys

# Third-party imports
from fastapi import APIRouter, HTTPException, Depends, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

# Local imports
from core.settings import get_app_settings
from db.database import get_db
from db.models import User, Session as UserSession
from services.email import email_service
```

**JavaScript Pattern:**
```javascript
// React/Framework imports
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

// Third-party imports
import axios from 'axios';

// Local imports
import { useAuth } from '../hooks/useAuth';
import LoginForm from '../components/LoginForm';
import Layout from '../components/Layout';
```

**Path Aliases:**
- No path aliases detected in frontend (uses relative paths)
- JavaScript imports use relative paths like `../context/AuthContext`

## Error Handling

**Python Pattern:**
- Use FastAPI's `HTTPException` for API errors with status codes and detail messages
- Custom error response format: `APIErrorResponse` with nested `APIErrorDetail` containing `code`, `message`, and optional `details`
- Error logging via `log_system_error()` utility from `db.database`
- Example: `raise HTTPException(status_code=409, detail="Email already registered")`

**JavaScript Pattern:**
- Try-catch blocks in async functions
- Error extraction from response data: check for `data.error` or `data.detail`
- Return error objects with `success: false` and `error: message` fields
- Example:
```javascript
catch (err) {
  const message = err.message || 'Login failed';
  setError(message);
  return { success: false, error: message };
}
```

## Logging

**Framework:**
- Python: `logging` module
- JavaScript: `console.log()` for development (no centralized logger)

**Python Patterns:**
- Module-level logger: `logger = logging.getLogger("cryptotrader.service_name")`
- Named loggers follow dot notation: `logging.getLogger("cryptotrader.kraken_alerts")`
- Used in `api/auth.py`, `api/errors.py`, `main.py`, etc.
- Error logging through centralized `log_system_error()` from database module
- Example: `logger = logging.getLogger("cryptotrader.auth")`

**JavaScript Patterns:**
- Development logging: `console.log('Rendering App component');`
- No structured logging framework
- Used sparingly in production code

## Comments

**When to Comment:**
- Python: Docstrings for all functions/classes with Args, Returns, Raises sections
- Function-level comments explain complex logic (rarely needed)
- Inline comments for non-obvious algorithm decisions

**JSDoc/TSDoc:**
- JavaScript: JSDoc blocks for functions explaining purpose, parameters, return values, and errors
- Example from `useAuth.js`:
```javascript
/**
 * Custom hook for authentication.
 *
 * @returns {Object} Auth context with user, loading, error, and auth methods
 * @throws {Error} If used outside of AuthProvider
 */
```

- Python docstring style:
```python
def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password string
    """
```

## Function Design

**Size:**
- Python: Functions typically 10-50 lines, with complex business logic split across multiple functions
- JavaScript: Functional components and hooks tend to be 40-100+ lines with multiple effects/state handlers

**Parameters:**
- Python: Use Pydantic models for request validation (e.g., `RegisterRequest`, `LoginRequest`)
- JavaScript: Props objects for components, individual parameters for utility functions

**Return Values:**
- Python: Return Pydantic response models or raise HTTPException for errors
- JavaScript: Return objects with `success` boolean and `data`/`error` fields:
```javascript
return { success: true, data: response.data };
return { success: false, error: message };
```

## Module Design

**Exports:**
- Python: Direct imports of classes/functions - no barrel pattern
- JavaScript: ESM module exports with named exports and default exports
  - Example: `export default Layout;` and `export const useAuth = () => { ... }`

**Barrel Files:**
- Not used in this codebase

**Database Models:**
- SQLAlchemy models in `backend/db/models.py` follow PascalCase class names
- Tablenames use `snake_case`: `__tablename__ = "users"`
- Relationships defined with `relationship()` and `back_populates`

---

*Convention analysis: 2026-02-04*

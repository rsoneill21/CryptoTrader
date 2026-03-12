/**
 * Theme context for dark/light mode toggle.
 */

import React, { createContext, useState, useEffect, useCallback, useContext } from 'react';

const ThemeContext = createContext(null);

const THEME_KEY = 'cryptotrader_theme';

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(() => {
    // Check localStorage or default to dark
    const saved = localStorage.getItem(THEME_KEY);
    return saved || 'dark';
  });

  // Apply theme class to document
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
      root.classList.remove('light');
    } else {
      root.classList.add('light');
      root.classList.remove('dark');
    }
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  }, []);

  const setDarkTheme = useCallback(() => setTheme('dark'), []);
  const setLightTheme = useCallback(() => setTheme('light'), []);

  const value = {
    theme,
    isDark: theme === 'dark',
    toggleTheme,
    setDarkTheme,
    setLightTheme,
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export default ThemeContext;

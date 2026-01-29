/**
 * Main layout component wrapping authenticated pages.
 */

import React, { useState, useEffect } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';

const SIDEBAR_KEY = 'cryptotrader_sidebar';

const Layout = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    // Check localStorage or default to open on desktop
    const saved = localStorage.getItem(SIDEBAR_KEY);
    if (saved !== null) {
      return saved === 'true';
    }
    // Default: open on desktop, closed on mobile
    return window.innerWidth >= 1024;
  });

  // Persist sidebar state
  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, sidebarOpen.toString());
  }, [sidebarOpen]);

  // Close sidebar on mobile when route changes
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) {
        setSidebarOpen(false);
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  return (
    <div className="min-h-screen bg-gray-900 dark:bg-gray-900 light:bg-gray-50">
      <Sidebar isOpen={sidebarOpen} onToggle={toggleSidebar} />

      {/* Main content area */}
      <div
        className={`
          transition-all duration-300 ease-in-out
          ${sidebarOpen ? 'lg:ml-64' : 'lg:ml-16'}
        `}
      >
        <Header sidebarOpen={sidebarOpen} onToggleSidebar={toggleSidebar} />

        <main className="p-4 lg:p-6">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;

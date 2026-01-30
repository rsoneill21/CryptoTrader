/**
 * Main layout component wrapping authenticated pages.
 */

import React, { useState, useEffect } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';
import AlertNotification from './AlertNotification';

const SIDEBAR_KEY = 'cryptotrader_sidebar';

const Layout = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(() => {
    if (typeof window === 'undefined') {
      return true;
    }
    const saved = window.localStorage.getItem(SIDEBAR_KEY);
    if (saved !== null) {
      return saved === 'true';
    }
    return window.innerWidth >= 1024;
  });

  // Persist sidebar state
  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, sidebarOpen.toString());
  }, [sidebarOpen]);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) {
        setSidebarOpen(false);
        return;
      }
      setSidebarOpen(true);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const toggleSidebar = () => {
    setSidebarOpen((prev) => !prev);
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-gradient-to-br from-slate-950 via-gray-900 to-black text-white">
      <AlertNotification />
      <Sidebar isOpen={sidebarOpen} onToggle={toggleSidebar} />

      {/* Main content area */}
      <div
        className={`
          min-h-screen
          transition-all duration-300 ease-in-out
          ${sidebarOpen ? 'lg:ml-72' : 'lg:ml-20'}
        `}
      >
        <Header sidebarOpen={sidebarOpen} onToggleSidebar={toggleSidebar} />

        <main className="flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;

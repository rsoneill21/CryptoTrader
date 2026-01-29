/**
 * Hook to access authentication context.
 */

import { useContext } from 'react';
import { AuthContext } from '../context/AuthContext';

/**
 * Custom hook for authentication.
 *
 * @returns {Object} Auth context with user, loading, error, and auth methods
 * @throws {Error} If used outside of AuthProvider
 */
export const useAuth = () => {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }

  return context;
};

export default useAuth;

'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { getToken, setToken, removeToken, isAuthenticated, isAdmin } from '@/lib/auth';

interface AuthContextValue {
  isLoggedIn: boolean;
  isAdminUser: boolean;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  isLoggedIn: false,
  isAdminUser: false,
  signIn: () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(false);
  const [isAdminUser, setIsAdminUser] = useState<boolean>(false);

  useEffect(() => {
    setIsLoggedIn(isAuthenticated());
    setIsAdminUser(isAdmin());
  }, []);

  const signIn = useCallback((token: string) => {
    setToken(token);
    setIsLoggedIn(true);
    setIsAdminUser(isAdmin());
  }, []);

  const signOut = useCallback(() => {
    removeToken();
    setIsLoggedIn(false);
    setIsAdminUser(false);
  }, []);

  return (
    <AuthContext.Provider value={{ isLoggedIn, isAdminUser, signIn, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

// Re-export getToken so pages can access it without importing from lib/auth directly
export { getToken };

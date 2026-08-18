'use client';

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { getToken, setToken, removeToken, isAuthenticated, isAdmin, getCurrentUserEmail, getDisplayName } from '@/lib/auth';

interface AuthContextValue {
  isLoggedIn: boolean;
  isAdminUser: boolean;
  authReady: boolean;
  displayName: string | null;
  email: string | null;
  signIn: (token: string) => void;
  signOut: () => void;
}

const AuthContext = createContext<AuthContextValue>({
  isLoggedIn: false,
  isAdminUser: false,
  authReady: false,
  displayName: null,
  email: null,
  signIn: () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isLoggedIn, setIsLoggedIn] = useState<boolean>(false);
  const [isAdminUser, setIsAdminUser] = useState<boolean>(false);
  const [authReady, setAuthReady] = useState<boolean>(false);
  const [displayName, setDisplayName] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);

  useEffect(() => {
    setIsLoggedIn(isAuthenticated());
    setIsAdminUser(isAdmin());
    setDisplayName(getDisplayName());
    setEmail(getCurrentUserEmail());
    setAuthReady(true);
  }, []);

  const signIn = useCallback((token: string) => {
    setToken(token);
    setIsLoggedIn(true);
    setIsAdminUser(isAdmin());
    setDisplayName(getDisplayName());
    setEmail(getCurrentUserEmail());
  }, []);

  const signOut = useCallback(() => {
    removeToken();
    setIsLoggedIn(false);
    setIsAdminUser(false);
    setDisplayName(null);
    setEmail(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ isLoggedIn, isAdminUser, authReady, displayName, email, signIn, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

// Re-export getToken so pages can access it without importing from lib/auth directly
export { getToken };

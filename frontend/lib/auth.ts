// JWT storage and decode helpers
// Stores JWT in localStorage under the key 'wl_token'

const TOKEN_KEY = 'wl_token';

export function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function removeToken(): void {
  if (typeof window === 'undefined') return;
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  const token = getToken();
  if (!token) return false;
  try {
    const payload = decodeJwtPayload(token);
    if (!payload || !payload.exp) return true; // no expiry claim → treat as valid
    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

interface JwtPayload {
  sub?: string;
  email?: string;
  is_admin?: boolean;
  exp?: number;
  iat?: number;
}

export function decodeJwtPayload(token: string): JwtPayload | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(base64);
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export function getCurrentUserEmail(): string | null {
  const token = getToken();
  if (!token) return null;
  const payload = decodeJwtPayload(token);
  return payload?.email ?? payload?.sub ?? null;
}

export function isAdmin(): boolean {
  const token = getToken();
  if (!token) return false;
  const payload = decodeJwtPayload(token);
  return payload?.is_admin === true;
}

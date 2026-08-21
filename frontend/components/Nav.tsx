'use client';

import { useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';

// Edit by hand to match the season/month — e.g. a festival or wedding-season variant.
const NAV_TAGLINE = 'Har Event. Sabki Pics.';

export default function Nav() {
  const { isLoggedIn, isAdminUser, authReady, displayName, email, signOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    function handlePointerDown(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setMenuOpen(false);
    }
    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [menuOpen]);

  function handleSignOut() {
    setMenuOpen(false);
    signOut();
    router.push('/login');
  }

  const initial = (displayName ?? '?').charAt(0).toUpperCase();

  // Guest routes keep the PicsLeLo brand for identity, but never the
  // Login/Register/Dashboard/profile links, none of which a guest can use.
  // See docs/decisions for rationale.
  const isGuestRoute = pathname?.startsWith('/g/') ?? false;
  const guestSlug = isGuestRoute ? pathname?.split('/')[2] : undefined;
  const brandHref = isGuestRoute
    ? guestSlug
      ? `/g/${guestSlug}/gallery`
      : '/'
    : isLoggedIn
      ? '/dashboard'
      : '/';

  return (
    <header className="nav-app">
      <Link href={brandHref} className="nav-brand">
        <span className="nav-brand-row">
          <Image
            src="/logo-wordmark.png"
            alt="PicsLeLo"
            width={156}
            height={32}
            className="nav-brand-mark"
            priority
          />
          <span className="tag tag-outline nav-beta-tag">Beta</span>
        </span>
        <span className="nav-tagline">{NAV_TAGLINE}</span>
      </Link>
      {isGuestRoute ? null : !authReady ? (
        <div className="h-8 w-32" />
      ) : isLoggedIn ? (
        <nav className="flex items-center gap-5">
          <Link href="/dashboard" className="nav-link">
            Dashboard
          </Link>
          {isAdminUser && (
            <Link href="/admin" className="nav-link">
              Admin
            </Link>
          )}
          <div className="nav-profile" ref={menuRef}>
            <button
              type="button"
              className="nav-profile-trigger"
              onClick={() => setMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
            >
              <span className="nav-avatar" aria-hidden="true">
                {initial}
              </span>
              {displayName && <span className="nav-profile-name">{displayName}</span>}
              <svg
                className="nav-profile-caret"
                viewBox="0 0 10 6"
                fill="none"
                aria-hidden="true"
              >
                <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
            {menuOpen && (
              <div className="nav-dropdown" role="menu">
                {email && <div className="nav-dropdown-header">{email}</div>}
                <button
                  type="button"
                  role="menuitem"
                  className="nav-dropdown-item"
                  onClick={handleSignOut}
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </nav>
      ) : (
        <nav className="flex items-center gap-4">
          <Link href="/login" className="nav-link">
            Log in
          </Link>
          <Link href="/register" className="btn btn-primary">
            Register
          </Link>
        </nav>
      )}
    </header>
  );
}

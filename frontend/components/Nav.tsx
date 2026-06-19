'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from './AuthProvider';

export default function Nav() {
  const { isLoggedIn, isAdminUser, signOut } = useAuth();
  const router = useRouter();

  function handleSignOut() {
    signOut();
    router.push('/login');
  }

  return (
    <header className="bg-white border-b border-gray-200">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="text-lg font-bold text-gray-900">
          WeddingLens
        </Link>
        {isLoggedIn ? (
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/dashboard" className="text-gray-600 hover:text-gray-900">
              Dashboard
            </Link>
            {isAdminUser && (
              <Link href="/admin" className="text-gray-600 hover:text-gray-900">
                Admin
              </Link>
            )}
            <button
              onClick={handleSignOut}
              className="text-gray-600 hover:text-gray-900 focus:outline-none"
            >
              Sign out
            </button>
          </nav>
        ) : (
          <nav className="flex items-center gap-4 text-sm">
            <Link href="/login" className="text-gray-600 hover:text-gray-900">
              Log in
            </Link>
            <Link
              href="/register"
              className="bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700"
            >
              Register
            </Link>
          </nav>
        )}
      </div>
    </header>
  );
}

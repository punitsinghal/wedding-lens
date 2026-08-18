'use client';

import { useState, FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { login } from '@/lib/api';
import { useAuth } from '@/components/AuthProvider';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { signIn } = useAuth();
  const router = useRouter();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setIsLoading(true);
    try {
      const { access_token } = await login(email, password);
      signIn(access_token);
      router.replace('/dashboard');
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Invalid email or password.');
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl mb-1">Sign in</h1>
        <p className="text-sm opacity-60 mb-6">
          Don&apos;t have an account?{' '}
          <Link href="/register" className="text-accent hover:underline">
            Register
          </Link>
        </p>

        {error && (
          <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="field">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="input"
            />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              className="input"
            />
          </div>
          <button type="submit" disabled={isLoading} className="btn btn-primary btn-block">
            {isLoading ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect, FormEvent } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { getEventBySlug, guestAuth } from '@/lib/api';
import { setGuestToken, isGuestAuthenticated } from '@/lib/auth';
import type { EventPublicOut } from '@/types/api';

export default function GuestEntryPage() {
  const router = useRouter();
  const params = useParams();
  const slug = params.slug as string;

  const [event, setEvent] = useState<EventPublicOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [code, setCode] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  useEffect(() => {
    getEventBySlug(slug)
      .then((ev) => {
        setEvent(ev);
        if (ev.status === 'published' && ev.access_mode === 'public') {
          router.replace(`/g/${slug}/gallery`);
          return;
        }
        if (isGuestAuthenticated(ev.id)) {
          const nextParam = new URLSearchParams(window.location.search).get('next');
          router.replace(nextParam ?? `/g/${slug}/gallery`);
        }
      })
      .catch(() => {
        setLoadError('not_found');
      })
      .finally(() => setIsLoading(false));
  }, [slug, router]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!event) return;
    setSubmitError('');
    setIsSubmitting(true);
    try {
      const token = await guestAuth(event.id, code.trim());
      setGuestToken(event.id, token.access_token);
      const nextParam = new URLSearchParams(window.location.search).get('next');
      router.replace(nextParam ?? `/g/${slug}/gallery`);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string; status?: number };
      // Check for 429 rate-limit — the thrown body may carry a status or detail
      const detail = apiErr?.detail ?? '';
      if (detail.toLowerCase().includes('too many') || detail.toLowerCase().includes('lockout')) {
        setSubmitError('Too many attempts. Try again in 15 minutes.');
      } else if (detail.toLowerCase().includes('revoked') || detail.toLowerCase().includes('inaccessible')) {
        setSubmitError('Guest access to this event has been disabled. Contact the photographer.');
      } else {
        setSubmitError('Invalid code. Please check and try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  if (loadError === 'not_found' || !event) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Event not found</h1>
          <p className="text-sm text-gray-500">
            This link may be incorrect or the event may have been removed.
          </p>
        </div>
      </div>
    );
  }

  if (event.status !== 'published') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-xl font-semibold text-gray-800 mb-2">{event.name}</h1>
          <p className="text-sm text-gray-500">This event is currently unavailable.</p>
        </div>
      </div>
    );
  }

  // Public mode — show brief message while redirect happens
  if (event.access_mode === 'public') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <p className="text-gray-500 text-sm">Entering gallery...</p>
      </div>
    );
  }

  const isOtp = event.access_mode === 'magic-link-otp';
  const inputLabel = isOtp ? 'OTP Code' : 'Access Code';
  const inputPlaceholder = isOtp ? 'Enter OTP code' : 'Enter access code';

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-gray-50">
      <div className="max-w-sm w-full bg-white border border-gray-200 rounded-xl shadow-sm p-8">
        {/* Event heading */}
        <div className="text-center mb-6">
          <h1 className="text-2xl font-bold text-gray-900">{event.name}</h1>
          {event.bride_name && event.groom_name && (
            <p className="mt-1 text-sm text-gray-500">
              {event.bride_name} &amp; {event.groom_name}
            </p>
          )}
          {event.event_date && (
            <p className="mt-0.5 text-xs text-gray-400">
              {new Date(event.event_date).toLocaleDateString(undefined, {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="code"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              {inputLabel}
            </label>
            <input
              id="code"
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder={inputPlaceholder}
              required
              autoComplete="off"
              autoFocus
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            {submitError && (
              <p className="mt-1.5 text-xs text-red-600">{submitError}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={isSubmitting || !code.trim()}
            className="w-full px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Verifying...' : 'Enter Gallery'}
          </button>
        </form>
      </div>
    </div>
  );
}

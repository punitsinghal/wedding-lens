'use client';

import { useState, FormEvent, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { createEvent } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { generateSlug, validateSlug } from '@/lib/slugUtils';
import { isSlugTakenError } from '@/types/api';
import type { AccessMode } from '@/types/api';
import SlugField from '@/components/SlugField';

function InfoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="8" cy="8" r="6.25" stroke="currentColor" strokeWidth="1.4" />
      <path d="M8 7.25v3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      <circle cx="8" cy="5.1" r="0.85" fill="currentColor" />
    </svg>
  );
}

export default function NewEventPage() {
  const router = useRouter();

  // Auth guard
  useEffect(() => {
    if (!isAuthenticated()) router.replace('/login');
  }, [router]);

  const [name, setName] = useState('');
  const [brideName, setBrideName] = useState('');
  const [groomName, setGroomName] = useState('');
  const [eventDate, setEventDate] = useState('');
  const [accessMode, setAccessMode] = useState<AccessMode>('public');
  const [accessCode, setAccessCode] = useState('');
  const [slug, setSlug] = useState('');
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);
  const [slugSuggestions, setSlugSuggestions] = useState<string[]>([]);

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  // Auto-generate slug from bride + groom names unless manually edited
  useEffect(() => {
    if (!slugManuallyEdited && (brideName || groomName)) {
      setSlug(generateSlug(brideName, groomName));
    }
  }, [brideName, groomName, slugManuallyEdited]);

  function handleSlugChange(value: string) {
    setSlug(value);
    setSlugManuallyEdited(true);
    setSlugSuggestions([]);
  }

  function handleSelectSuggestion(suggestion: string) {
    setSlug(suggestion);
    setSlugManuallyEdited(true);
    setSlugSuggestions([]);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError('');
    setSlugSuggestions([]);

    const slugError = validateSlug(slug);
    if (slugError) {
      setError(slugError);
      return;
    }

    if (accessMode === 'access-code' && !accessCode.trim()) {
      setError('Access code is required for access-code mode.');
      return;
    }

    setIsLoading(true);
    try {
      const event = await createEvent({
        name: name.trim(),
        bride_name: brideName.trim(),
        groom_name: groomName.trim(),
        event_date: eventDate,
        access_mode: accessMode,
        ...(accessMode === 'access-code' ? { access_code: accessCode.trim() } : {}),
        slug: slug.trim(),
      });
      router.push(`/events/${event.id}`);
    } catch (err: unknown) {
      if (isSlugTakenError(err)) {
        setSlugSuggestions(err.suggestions);
        setError('That URL slug is already taken. Please choose another or pick a suggestion below.');
      } else {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to create event.');
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-10">
      <div className="grid grid-cols-1 md:grid-cols-[1fr,300px] gap-11">
        {/* Left column — form */}
        <div>
          <h1 className="text-4xl mb-6">New event</h1>

          {error && (
            <div className="mb-6 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Event name */}
            <div className="field">
              <label htmlFor="name">
                Event Name <span className="text-accent">*</span>
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                placeholder="e.g. Priya & Rahul Wedding"
                className="input"
              />
            </div>

            {/* Bride & Groom names */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="field">
                <label htmlFor="brideName">
                  Bride&apos;s Name <span className="text-accent">*</span>
                </label>
                <input
                  id="brideName"
                  type="text"
                  value={brideName}
                  onChange={(e) => setBrideName(e.target.value)}
                  required
                  placeholder="Priya"
                  className="input"
                />
              </div>
              <div className="field">
                <label htmlFor="groomName">
                  Groom&apos;s Name <span className="text-accent">*</span>
                </label>
                <input
                  id="groomName"
                  type="text"
                  value={groomName}
                  onChange={(e) => setGroomName(e.target.value)}
                  required
                  placeholder="Rahul"
                  className="input"
                />
              </div>
            </div>

            {/* Event date */}
            <div className="field">
              <label htmlFor="eventDate">
                Event Date <span className="text-accent">*</span>
              </label>
              <input
                id="eventDate"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                required
                className="input"
              />
            </div>

            {/* Access mode */}
            <div className="field">
              <label>
                Guest Access Mode <span className="text-accent">*</span>
              </label>
              <div className="flex flex-col gap-3">
                <label className="radio">
                  <input
                    type="radio"
                    name="accessMode"
                    value="public"
                    checked={accessMode === 'public'}
                    onChange={() => setAccessMode('public')}
                  />
                  <span className="dot" />
                  <span>
                    Public
                    <span className="block text-xs opacity-60">Anyone with the link can view</span>
                  </span>
                </label>
                <label className="radio">
                  <input
                    type="radio"
                    name="accessMode"
                    value="access-code"
                    checked={accessMode === 'access-code'}
                    onChange={() => setAccessMode('access-code')}
                  />
                  <span className="dot" />
                  <span>
                    Access Code
                    <span className="block text-xs opacity-60">Guests enter a code to view</span>
                  </span>
                </label>
                <label className="radio">
                  <input
                    type="radio"
                    name="accessMode"
                    value="magic-link-otp"
                    checked={accessMode === 'magic-link-otp'}
                    onChange={() => setAccessMode('magic-link-otp')}
                  />
                  <span className="dot" />
                  <span>
                    Magic Link / OTP
                    <span className="block text-xs opacity-60">Guests verify by email</span>
                  </span>
                </label>
              </div>
            </div>

            {/* Access code (conditional) */}
            {accessMode === 'access-code' && (
              <div className="field">
                <label htmlFor="accessCode">
                  Access Code <span className="text-accent">*</span>
                </label>
                <input
                  id="accessCode"
                  type="text"
                  value={accessCode}
                  onChange={(e) => setAccessCode(e.target.value)}
                  required
                  placeholder="e.g. PRIYA2026"
                  className="input"
                />
                <p className="mt-1 text-xs opacity-60">
                  Share this code with your guests. They will need it to access the gallery.
                </p>
              </div>
            )}

            {/* Slug */}
            <SlugField
              value={slug}
              onChange={handleSlugChange}
              suggestions={slugSuggestions}
              onSelectSuggestion={handleSelectSuggestion}
            />

            <div className="flex justify-end gap-3 pt-2">
              <Link href="/dashboard" className="btn btn-secondary">
                Cancel
              </Link>
              <button type="submit" disabled={isLoading} className="btn btn-primary">
                {isLoading ? 'Creating...' : 'Create event'}
              </button>
            </div>
          </form>
        </div>

        {/* Right column — info card */}
        <aside className="card elev-sm bg-accent-2-100 h-fit">
          <div className="w-9 h-9 rounded-full bg-accent-2-500 text-bg grid place-items-center">
            <InfoIcon />
          </div>
          <h2 className="card-title">What happens next</h2>
          <p className="card-body">
            Once your event is created, you&apos;ll upload photos, set a cover photo, and publish
            when you&apos;re ready. Nothing is visible to guests until you publish.
          </p>
        </aside>
      </div>
    </div>
  );
}

'use client';

import { useState, FormEvent, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createEvent } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import { generateSlug, validateSlug } from '@/lib/slugUtils';
import { isSlugTakenError } from '@/types/api';
import type { AccessMode } from '@/types/api';
import SlugField from '@/components/SlugField';

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
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Create New Event</h1>
        <p className="text-sm text-gray-500 mt-1">
          Set up your wedding event. You can edit all details later.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-5 bg-white border border-gray-200 rounded-lg p-6">
        {/* Event name */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="name">
            Event Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            placeholder="e.g. Priya & Rahul Wedding"
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Bride & Groom names */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="brideName">
              Bride&apos;s Name <span className="text-red-500">*</span>
            </label>
            <input
              id="brideName"
              type="text"
              value={brideName}
              onChange={(e) => setBrideName(e.target.value)}
              required
              placeholder="Priya"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="groomName">
              Groom&apos;s Name <span className="text-red-500">*</span>
            </label>
            <input
              id="groomName"
              type="text"
              value={groomName}
              onChange={(e) => setGroomName(e.target.value)}
              required
              placeholder="Rahul"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>

        {/* Event date */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="eventDate">
            Event Date <span className="text-red-500">*</span>
          </label>
          <input
            id="eventDate"
            type="date"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
            required
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        {/* Access mode */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="accessMode">
            Guest Access Mode <span className="text-red-500">*</span>
          </label>
          <select
            id="accessMode"
            value={accessMode}
            onChange={(e) => setAccessMode(e.target.value as AccessMode)}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="public">Public — anyone with the link</option>
            <option value="access-code">Access Code — guests enter a code</option>
            <option value="magic-link-otp">Magic Link / OTP — guests verify by email</option>
          </select>
        </div>

        {/* Access code (conditional) */}
        {accessMode === 'access-code' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="accessCode">
              Access Code <span className="text-red-500">*</span>
            </label>
            <input
              id="accessCode"
              type="text"
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
              required
              placeholder="e.g. PRIYA2026"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <p className="mt-1 text-xs text-gray-400">
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
          <button
            type="button"
            onClick={() => router.back()}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isLoading ? 'Creating...' : 'Create Event'}
          </button>
        </div>
      </form>
    </div>
  );
}

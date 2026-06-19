'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getDashboardEvents } from '@/lib/api';
import type { Event } from '@/types/api';
import EventCard from '@/components/EventCard';

export default function DashboardPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getDashboardEvents()
      .then(setEvents)
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to load events.');
      })
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">My Events</h1>
        <Link
          href="/events/new"
          className="bg-blue-600 text-white text-sm font-medium px-4 py-2 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          + New Event
        </Link>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading events...</div>
      ) : events.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-gray-300 rounded-lg">
          <p className="text-gray-500 text-sm mb-4">No events yet.</p>
          <Link
            href="/events/new"
            className="text-blue-600 text-sm hover:underline font-medium"
          >
            Create your first event
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {events.map((event) => (
            <EventCard key={event.id} event={event} />
          ))}
        </div>
      )}
    </div>
  );
}

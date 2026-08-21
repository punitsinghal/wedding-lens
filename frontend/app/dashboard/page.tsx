'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { getDashboardEvents, getMyAssignedEvents } from '@/lib/api';
import type { Event, AssignedEvent } from '@/types/api';
import EventCard from '@/components/EventCard';
import AssignedEventCard from '@/components/AssignedEventCard';
import ErrorBoundary from '@/components/ErrorBoundary';

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  );
}

export default function DashboardPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [assignedEvents, setAssignedEvents] = useState<AssignedEvent[]>([]);
  const [assignedEventsError, setAssignedEventsError] = useState('');

  useEffect(() => {
    Promise.allSettled([getDashboardEvents(), getMyAssignedEvents()])
      .then(([ownedResult, assignedResult]) => {
        if (ownedResult.status === 'fulfilled') setEvents(ownedResult.value);
        else {
          const err = ownedResult.reason as { detail?: string };
          setError(err?.detail ?? 'Failed to load events.');
        }
        if (assignedResult.status === 'fulfilled') setAssignedEvents(assignedResult.value.events as AssignedEvent[]);
        else setAssignedEventsError('Could not load assigned events');
      })
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10">
      <div className="flex items-center justify-between gap-4 mb-8">
        <h1 className="text-4xl">Your events</h1>
        <Link href="/events/new" className="btn btn-primary">
          <PlusIcon />
          New event
        </Link>
      </div>

      {error && (
        <div className="mb-6 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error}
        </div>
      )}

      <ErrorBoundary
        fallback={
          <div className="mb-6 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
            Could not load events — try refreshing.
          </div>
        }
      >
        {isLoading ? (
          <div className="text-center py-16 text-neutral-600 text-sm">Loading events...</div>
        ) : events.length === 0 ? (
          <div className="text-center py-16 border-2 border-dashed border-divider rounded-lg">
            <p className="text-neutral-600 text-sm mb-4">No events yet.</p>
            <Link href="/events/new" className="btn btn-primary">
              <PlusIcon />
              Create your first event
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {events.map((event) => (
              <EventCard key={event.id} event={event} />
            ))}
            <Link
              href="/events/new"
              className="flex flex-col items-center justify-center gap-2 min-h-[240px] rounded-lg border-2 border-dashed border-divider text-neutral-600 hover:border-accent hover:text-accent transition-colors text-center p-6"
            >
              <PlusIcon />
              <span className="text-sm font-medium">Create your next event</span>
            </Link>
          </div>
        )}
      </ErrorBoundary>

      {assignedEventsError && (
        <div className="mt-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {assignedEventsError}
        </div>
      )}
      {assignedEvents.length > 0 && (
        <div className="mt-12">
          <h2 className="text-2xl mb-4">Events I&apos;m Photographing</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {assignedEvents.map((event) => (
              <AssignedEventCard key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

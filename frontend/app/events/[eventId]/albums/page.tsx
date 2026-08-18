'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getEvent, getAlbums } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import type { Event, Album } from '@/types/api';
import AlbumList, { MAX_ALBUMS } from '@/components/AlbumList';
import StatusBadge from '@/components/StatusBadge';

export default function AlbumsPage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.eventId as string;

  useEffect(() => {
    if (!isAuthenticated()) router.replace('/login');
  }, [router]);

  const [event, setEvent] = useState<Event | null>(null);
  const [albums, setAlbums] = useState<Album[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    Promise.all([getEvent(eventId), getAlbums(eventId)])
      .then(([ev, alb]) => {
        setEvent(ev);
        setAlbums(alb);
      })
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to load data.');
      })
      .finally(() => setIsLoading(false));
  }, [eventId]);

  if (isLoading) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-16 text-center text-sm opacity-60">
        Loading...
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8">
        <div className="px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error || 'Event not found.'}
        </div>
        <Link href="/dashboard" className="btn btn-secondary mt-4">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <p className="text-sm opacity-60 mb-1 flex items-center gap-2 flex-wrap">
        <Link href="/dashboard" className="hover:text-accent">Dashboard</Link> /{' '}
        <Link href={`/events/${eventId}`} className="hover:text-accent truncate">
          {event.name}
        </Link>{' '}
        / Albums
        <StatusBadge status={event.status} />
      </p>
      <h1 className="text-3xl sm:text-4xl mb-1">Albums</h1>
      <p className="text-sm opacity-60 mb-6">
        {albums.length} of {MAX_ALBUMS} used
      </p>

      <AlbumList eventId={eventId} initialAlbums={albums} />
    </div>
  );
}

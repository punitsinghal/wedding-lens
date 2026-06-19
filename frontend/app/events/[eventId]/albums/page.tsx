'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getEvent, getAlbums } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import type { Event, Album } from '@/types/api';
import AlbumList from '@/components/AlbumList';
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
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-gray-400 text-sm">
        Loading...
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error || 'Event not found.'}
        </div>
        <Link href="/dashboard" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 text-sm flex-wrap">
        <Link href="/dashboard" className="text-gray-500 hover:text-gray-700">
          Dashboard
        </Link>
        <span className="text-gray-300">/</span>
        <Link href={`/events/${eventId}`} className="text-gray-500 hover:text-gray-700 truncate">
          {event.name}
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-900 font-medium">Albums</span>
        <StatusBadge status={event.status} />
      </div>

      <AlbumList eventId={eventId} initialAlbums={albums} />
    </div>
  );
}

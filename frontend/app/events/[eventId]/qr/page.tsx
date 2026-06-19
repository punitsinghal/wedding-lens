'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getEvent, getQrCodeUrl } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import type { Event } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';

export default function QrCodePage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.eventId as string;

  useEffect(() => {
    if (!isAuthenticated()) router.replace('/login');
  }, [router]);

  const [event, setEvent] = useState<Event | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    getEvent(eventId)
      .then(setEvent)
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to load event.');
      })
      .finally(() => setIsLoading(false));
  }, [eventId]);

  async function handleDownload() {
    const url = getQrCodeUrl(eventId);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch QR code');
      const blob = await res.blob();
      const objectUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = objectUrl;
      link.download = `${event?.slug ?? eventId}-qr.png`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(objectUrl);
    } catch {
      setError('Failed to download QR code. Please try again.');
    }
  }

  if (isLoading) {
    return (
      <div className="max-w-lg mx-auto px-4 py-16 text-center text-gray-400 text-sm">
        Loading...
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="max-w-lg mx-auto px-4 py-8">
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error || 'Event not found.'}
        </div>
        <Link href="/dashboard" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const qrUrl = getQrCodeUrl(eventId);

  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-8">
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
        <span className="text-gray-900 font-medium">QR Code</span>
        <StatusBadge status={event.status} />
      </div>

      <div className="bg-white border border-gray-200 rounded-lg p-6 text-center">
        <h1 className="text-xl font-bold text-gray-900 mb-1">{event.name}</h1>
        <p className="text-sm text-gray-500 mb-6">
          {event.bride_name} &amp; {event.groom_name}
        </p>

        {/* QR code image — proxied via Next.js API route */}
        <div className="inline-block border border-gray-200 rounded-lg p-4 bg-white mb-6">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={qrUrl}
            alt={`QR code for ${event.name}`}
            width={256}
            height={256}
            className="block"
          />
        </div>

        <p className="text-xs text-gray-400 font-mono mb-6">/{event.slug}</p>

        <button
          onClick={handleDownload}
          className="inline-flex items-center gap-2 bg-blue-600 text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          Download PNG
        </button>

        <p className="mt-4 text-xs text-gray-400">
          The QR code auto-updates if you change the event slug.
        </p>
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getEvent, getQrCodeUrl } from '@/lib/api';
import { isAuthenticated, getToken } from '@/lib/auth';
import type { Event } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M8 2v7.5M8 9.5 5.2 6.7M8 9.5l2.8-2.8"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M2.75 11.5v1.25c0 .55.45 1 1 1h8.5c.55 0 1-.45 1-1V11.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  );
}

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
  const [qrObjectUrl, setQrObjectUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [origin, setOrigin] = useState('');

  useEffect(() => {
    setOrigin(window.location.origin);
  }, []);

  useEffect(() => {
    getEvent(eventId)
      .then(setEvent)
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to load event.');
      })
      .finally(() => setIsLoading(false));
  }, [eventId]);

  // Fetch QR image with auth header and use a blob URL for display
  useEffect(() => {
    if (!eventId) return;
    const token = getToken();
    fetch(getQrCodeUrl(eventId), {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load QR code');
        return res.blob();
      })
      .then((blob) => setQrObjectUrl(URL.createObjectURL(blob)))
      .catch(() => setError('Failed to load QR code image.'));
    return () => {
      if (qrObjectUrl) URL.revokeObjectURL(qrObjectUrl);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId]);

  async function handleCopy(url: string) {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

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
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-sm opacity-60">
        Loading...
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
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
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
      {/* Breadcrumb */}
      <p className="text-sm opacity-60 mb-1 flex items-center gap-2 flex-wrap">
        <Link href="/dashboard" className="hover:text-accent">Dashboard</Link> /{' '}
        <Link href={`/events/${eventId}`} className="hover:text-accent truncate">
          {event.name}
        </Link>{' '}
        / QR Code
        <StatusBadge status={event.status} />
      </p>

      <div className="mt-5 grid grid-cols-1 md:grid-cols-[1fr,260px] gap-11 items-center">
        {/* Left column — link, copy, download */}
        <div>
          <h1 className="text-3xl sm:text-4xl mb-3">Hand this to your guests</h1>
          <p className="text-sm opacity-70 mb-6 max-w-md">
            This link and QR code always point at {event.name}&apos;s gallery. Share it, print
            it on table cards, or display it at the venue — guests scan or tap to find their own
            photos.
          </p>

          {origin && (
            <div className="mb-4 flex items-center gap-2 bg-neutral-100 rounded-full pl-4 pr-1.5 py-1.5">
              <a
                href={`${origin}/g/${event.slug}`}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 font-mono text-sm truncate hover:text-accent"
              >
                {origin}/g/{event.slug}
              </a>
              <button
                onClick={() => handleCopy(`${origin}/g/${event.slug}`)}
                className="btn btn-primary shrink-0"
              >
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            <button onClick={handleDownload} className="btn btn-secondary">
              <DownloadIcon />
              Download PNG
            </button>
          </div>
        </div>

        {/* Right column — QR panel */}
        <div className="card elev-sm bg-accent-2-100 items-center text-center p-7 rounded-[36px]">
          <div className="bg-bg rounded-[24px] shadow-sm p-4 inline-flex">
            {qrObjectUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={qrObjectUrl}
                alt={`QR code for ${event.name}`}
                width={200}
                height={200}
                className="block"
              />
            ) : (
              <div className="w-[200px] h-[200px] flex items-center justify-center text-sm opacity-50">
                Loading QR…
              </div>
            )}
          </div>
          <p className="mt-3 text-sm font-medium truncate max-w-full">{event.name}</p>
          <p className="text-xs text-accent-2-800">Scan for the photo gallery</p>
        </div>
      </div>
    </div>
  );
}

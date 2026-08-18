'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { resolveShareToken, guestFetchBlob, downloadPhoto } from '@/lib/api';
import { isGuestAuthenticated } from '@/lib/auth';
import PageLoading from '@/components/PageLoading';

type PageState = 'loading' | 'expired' | 'invalid' | 'unauthenticated' | 'ready';

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

export default function SharePage() {
  const params = useParams();
  const router = useRouter();
  const token = params.token as string;

  const [state, setState] = useState<PageState>('loading');
  const [photoId, setPhotoId] = useState('');
  const [eventId, setEventId] = useState('');
  const [eventSlug, setEventSlug] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    resolveShareToken(token)
      .then((data) => {
        setPhotoId(data.photo_id);
        setEventId(data.event_id);
        setEventSlug(data.event_slug);
        if (!isGuestAuthenticated(data.event_id)) {
          if (data.event_slug) {
            router.replace(`/g/${data.event_slug}?next=/share/${token}`);
          } else {
            setState('unauthenticated');
          }
          return;
        }
        setState('ready');
      })
      .catch((err: unknown) => {
        const detail = (err as { detail?: string })?.detail;
        if (detail === 'link_expired') setState('expired');
        else setState('invalid');
      });
  }, [token, router]);

  // Load photo blob when ready
  useEffect(() => {
    if (state !== 'ready' || !photoId || !eventId) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    const thumbnailPath = `/api/v1/events/${eventId}/photos/${photoId}/thumbnail`;
    guestFetchBlob(eventId, thumbnailPath)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [state, photoId, eventId]);

  if (state === 'loading') {
    return <PageLoading />;
  }

  if (state === 'expired') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-2xl mb-2">Link expired</h1>
          <p className="text-sm opacity-70 mb-5">
            This share link is no longer valid. Share links expire after 72 hours.
          </p>
          <Link href="/" className="btn btn-secondary">
            Go to home
          </Link>
        </div>
      </div>
    );
  }

  if (state === 'invalid') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-2xl mb-2">Invalid link</h1>
          <p className="text-sm opacity-70 mb-5">This link is not valid.</p>
          <Link href="/" className="btn btn-secondary">
            Go to home
          </Link>
        </div>
      </div>
    );
  }

  if (state === 'unauthenticated') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-2xl mb-2">Access required</h1>
          <p className="text-sm opacity-70 mb-5">
            You need to access the event gallery before viewing this shared photo.
          </p>
          <Link href="/" className="btn btn-secondary">
            Go to home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen relative bg-neutral-900">
      {blobUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={blobUrl}
          alt="Shared wedding photo"
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 animate-pulse bg-neutral-800" />
      )}
      <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/0 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 px-6 pb-10 pt-32 flex flex-col items-start gap-3">
        <span className="text-xs uppercase tracking-[0.14em] text-accent-300">
          Shared with you
        </span>
        <h1 className="text-3xl sm:text-4xl text-white">A shared photo</h1>
        <div className="flex flex-wrap gap-3 pt-2">
          <button
            onClick={() => downloadPhoto(eventId, photoId).catch(() => {})}
            className="btn btn-primary"
          >
            <DownloadIcon />
            Download
          </button>
          {eventSlug && (
            <Link href={`/g/${eventSlug}`} className="btn bg-white/15 text-bg">
              See the gallery
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

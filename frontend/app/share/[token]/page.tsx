'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { resolveShareToken, guestFetchBlob, downloadPhoto } from '@/lib/api';
import { isGuestAuthenticated } from '@/lib/auth';

type PageState = 'loading' | 'expired' | 'invalid' | 'unauthenticated' | 'ready';

export default function SharePage() {
  const params = useParams();
  const router = useRouter();
  const token = params.token as string;

  const [state, setState] = useState<PageState>('loading');
  const [photoId, setPhotoId] = useState('');
  const [eventId, setEventId] = useState('');
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    resolveShareToken(token)
      .then((data) => {
        setPhotoId(data.photo_id);
        setEventId(data.event_id);
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
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  if (state === 'expired') {
    return (
      <div className="min-h-screen flex items-center justify-center px-4">
        <div className="max-w-sm w-full text-center">
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Link expired</h1>
          <p className="text-sm text-gray-500 mb-4">
            This share link is no longer valid. Share links expire after 72 hours.
          </p>
          <Link href="/" className="text-sm text-blue-600 hover:underline">
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
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Invalid link</h1>
          <p className="text-sm text-gray-500 mb-4">This link is not valid.</p>
          <Link href="/" className="text-sm text-blue-600 hover:underline">
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
          <h1 className="text-xl font-semibold text-gray-800 mb-2">Access required</h1>
          <p className="text-sm text-gray-500 mb-4">
            You need to access the event gallery before viewing this shared photo.
          </p>
          <Link href="/" className="text-sm text-blue-600 hover:underline">
            Go to home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-4 py-8">
      <div className="max-w-2xl w-full">
        <h1 className="text-lg font-semibold text-gray-800 mb-4 text-center">Shared photo</h1>
        <div className="rounded-xl overflow-hidden bg-gray-200 aspect-square max-w-md mx-auto">
          {blobUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={blobUrl} alt="Shared wedding photo" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full animate-pulse bg-gray-200" />
          )}
        </div>
        <div className="mt-4 flex justify-center gap-3">
          <button
            onClick={() => downloadPhoto(eventId, photoId).catch(() => {})}
            className="px-4 py-2 text-sm font-medium bg-gray-900 text-white rounded-full hover:bg-gray-700 transition-colors"
          >
            Download original
          </button>
        </div>
      </div>
    </div>
  );
}

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAlbum, getEvent, getPhotos, updateAlbum, fetchAuthedBlob } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import type { Album, Event, Photo } from '@/types/api';

export default function AlbumDetailPage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.eventId as string;
  const albumId = params.albumId as string;

  const [event, setEvent] = useState<Event | null>(null);
  const [album, setAlbum] = useState<Album | null>(null);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [blobUrls, setBlobUrls] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [settingCover, setSettingCover] = useState<string | null>(null);

  // Track blob URLs for cleanup on unmount
  const blobUrlsRef = useRef<Record<string, string>>({});

  useEffect(() => {
    if (!isAuthenticated()) router.replace('/login');
  }, [router]);

  // Revoke all object URLs on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      Object.values(blobUrlsRef.current).forEach(URL.revokeObjectURL);
    };
  }, []);

  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError('');
    try {
      const [evt, alb, photoList] = await Promise.all([
        getEvent(eventId),
        getAlbum(eventId, albumId),
        getPhotos(eventId, { albumId }),
      ]);
      setEvent(evt);
      setAlbum(alb);
      setPhotos(photoList.items);

      // Fetch thumbnails concurrently; silently skip failures
      const map: Record<string, string> = {};
      await Promise.allSettled(
        photoList.items
          .filter((p) => p.thumbnail_url)
          .map(async (p) => {
            const url = await fetchAuthedBlob(p.thumbnail_url!);
            map[p.id] = url;
          })
      );
      blobUrlsRef.current = map;
      setBlobUrls({ ...map });
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Failed to load album.');
    } finally {
      setIsLoading(false);
    }
  }, [eventId, albumId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  async function handleSetCover(photo: Photo) {
    if (!album) return;
    setSettingCover(photo.id);
    try {
      const updated = await updateAlbum(eventId, albumId, { cover_photo_id: photo.id });
      setAlbum(updated);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Failed to set cover photo.');
    } finally {
      setSettingCover(null);
    }
  }

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-16 text-center text-gray-400 text-sm">
        Loading...
      </div>
    );
  }

  if (error || !album) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error || 'Album not found.'}
        </div>
        <Link
          href={`/events/${eventId}/albums`}
          className="mt-4 inline-block text-sm text-blue-600 hover:underline"
        >
          Back to Albums
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 text-sm flex-wrap">
        <Link href="/dashboard" className="text-gray-500 hover:text-gray-700">
          Dashboard
        </Link>
        <span className="text-gray-300">/</span>
        <Link href={`/events/${eventId}`} className="text-gray-500 hover:text-gray-700 truncate">
          {event?.name ?? eventId}
        </Link>
        <span className="text-gray-300">/</span>
        <Link href={`/events/${eventId}/albums`} className="text-gray-500 hover:text-gray-700">
          Albums
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-900 font-medium truncate">{album.name}</span>
      </div>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{album.name}</h1>
        {album.ceremony_category && (
          <span className="mt-1 inline-block text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
            {album.ceremony_category}
          </span>
        )}
        <p className="mt-2 text-sm text-gray-500">Click a photo to set it as the album cover.</p>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      {photos.length === 0 ? (
        <div className="py-16 text-center border border-dashed border-gray-200 rounded-lg">
          <p className="text-sm text-gray-500">No photos in this album yet.</p>
          <Link
            href={`/events/${eventId}/photos`}
            className="mt-3 inline-block text-sm text-blue-600 hover:underline"
          >
            Go to Photos to add some
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
          {photos.map((photo) => {
            const isCover = album.cover_photo_id === photo.id;
            const isBeingSet = settingCover === photo.id;
            const thumbSrc = blobUrls[photo.id];

            return (
              <button
                key={photo.id}
                onClick={() => handleSetCover(photo)}
                disabled={isBeingSet || settingCover !== null}
                className={[
                  'relative aspect-square rounded-lg overflow-hidden',
                  'transition-all duration-150 focus:outline-none',
                  isCover
                    ? 'ring-2 ring-blue-500 ring-offset-1'
                    : 'hover:ring-2 hover:ring-gray-400 hover:ring-offset-1',
                  isBeingSet ? 'opacity-60 cursor-wait' : 'cursor-pointer',
                  settingCover !== null && settingCover !== photo.id
                    ? 'opacity-50 cursor-not-allowed'
                    : '',
                ]
                  .filter(Boolean)
                  .join(' ')}
                title={isCover ? 'Current cover photo' : `Set "${photo.filename}" as cover`}
              >
                {/* Thumbnail or placeholder */}
                {thumbSrc ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={thumbSrc}
                    alt={photo.filename}
                    className="absolute inset-0 w-full h-full object-cover"
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center bg-gray-100 text-xs text-gray-500 font-medium px-2 text-center leading-tight">
                    <span className="line-clamp-3 break-all">{photo.filename}</span>
                  </div>
                )}

                {/* Cover checkmark overlay */}
                {isCover && (
                  <span className="absolute top-1.5 right-1.5 flex items-center justify-center w-5 h-5 bg-blue-500 rounded-full shadow">
                    <svg className="w-3 h-3 text-white" viewBox="0 0 12 12" fill="none">
                      <path
                        d="M2 6l3 3 5-5"
                        stroke="currentColor"
                        strokeWidth="1.8"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                )}

                {/* Loading spinner overlay */}
                {isBeingSet && (
                  <span className="absolute inset-0 flex items-center justify-center bg-white/60 rounded-lg">
                    <svg className="w-5 h-5 text-blue-500 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
                    </svg>
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {photos.length > 0 && (
        <p className="mt-4 text-xs text-gray-400">
          {photos.length} photo{photos.length !== 1 ? 's' : ''} in this album
          {album.cover_photo_id ? ' · Cover photo set' : ' · No cover photo set'}
        </p>
      )}
    </div>
  );
}

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getAlbum, getEvent, getPhotos, updateAlbum, fetchAuthedBlob } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import type { Album, Event, Photo } from '@/types/api';
import PageLoading from '@/components/PageLoading';

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
    return <PageLoading fullScreen={false} />;
  }

  if (error || !album) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
        <div className="px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error || 'Album not found.'}
        </div>
        <Link href="/dashboard" className="btn btn-secondary mt-4">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 text-sm flex-wrap opacity-80">
        <Link href="/dashboard" className="hover:text-accent">
          Dashboard
        </Link>
        <span className="opacity-50">/</span>
        <Link href={`/events/${eventId}`} className="hover:text-accent truncate">
          {event?.name ?? eventId}
        </Link>
        <span className="opacity-50">/</span>
        <Link href={`/events/${eventId}/albums`} className="hover:text-accent">
          Albums
        </Link>
        <span className="opacity-50">/</span>
        <span className="font-medium opacity-100 truncate">{album.name}</span>
      </div>

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl">{album.name}</h1>
        {album.ceremony_category && (
          <span className="mt-1 tag tag-neutral">
            {album.ceremony_category}
          </span>
        )}
        <p className="mt-2 text-sm opacity-60">Click a photo to set it as the album cover.</p>
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error}
        </div>
      )}

      {photos.length === 0 ? (
        <div className="py-16 text-center border border-dashed border-divider rounded-lg">
          <p className="text-sm opacity-60">No photos in this album yet.</p>
          <Link
            href={`/events/${eventId}/photos`}
            className="mt-3 inline-block text-sm text-accent hover:underline"
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
                    ? 'ring-2 ring-accent ring-offset-1'
                    : 'hover:ring-2 hover:ring-neutral-400 hover:ring-offset-1',
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
                  <div className="absolute inset-0 flex items-center justify-center bg-neutral-100 text-xs opacity-60 font-medium px-2 text-center leading-tight">
                    <span className="line-clamp-3 break-all">{photo.filename}</span>
                  </div>
                )}

                {/* Cover checkmark overlay */}
                {isCover && (
                  <span className="absolute top-1.5 right-1.5 flex items-center justify-center w-5 h-5 bg-accent rounded-full shadow">
                    <svg className="w-3 h-3 text-bg" viewBox="0 0 12 12" fill="none">
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
                  <span className="absolute inset-0 flex items-center justify-center bg-bg/60 rounded-lg">
                    <svg className="w-5 h-5 text-accent animate-spin" viewBox="0 0 24 24" fill="none">
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
        <p className="mt-4 text-xs opacity-50">
          {photos.length} photo{photos.length !== 1 ? 's' : ''} in this album
          {album.cover_photo_id ? ' · Cover photo set' : ' · No cover photo set'}
        </p>
      )}
    </div>
  );
}

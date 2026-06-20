'use client';

import { useEffect, useState, useCallback } from 'react';
import { guestFetchBlob } from '@/lib/api';
import type { GalleryPhoto } from '@/types/api';

interface LightboxProps {
  photos: GalleryPhoto[];
  currentIndex: number;
  eventId: string;
  total: number;
  onClose: () => void;
  onNavigate: (newIndex: number) => void;
  onFetchMore: () => Promise<void>;
}

export default function Lightbox({
  photos,
  currentIndex,
  eventId,
  total,
  onClose,
  onNavigate,
  onFetchMore,
}: LightboxProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const photo = photos[currentIndex] ?? null;
  const photoId = photo?.id ?? null;

  // Load thumbnail as display image for lightbox
  useEffect(() => {
    if (!photoId) return;

    let objectUrl: string | null = null;
    let cancelled = false;

    setBlobUrl(null);

    guestFetchBlob(eventId, photo.thumbnail_url ?? `/api/v1/events/${eventId}/photos/${photoId}/thumbnail`)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => {
        // leave blobUrl null
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [photoId, eventId, photo?.thumbnail_url]);

  const navigateTo = useCallback(
    async (newIndex: number) => {
      if (newIndex >= photos.length && photos.length < total) {
        await onFetchMore();
      }
      // Only advance if the photo now exists — onFetchMore may have been a no-op
      // (e.g. another load was already in flight), in which case photos.length
      // hasn't changed and newIndex is still out of bounds.
      if (newIndex < photos.length) {
        onNavigate(newIndex);
      }
    },
    [photos.length, total, onFetchMore, onNavigate]
  );

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') navigateTo(currentIndex + 1);
      if (e.key === 'ArrowLeft' && currentIndex > 0) navigateTo(currentIndex - 1);
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose, navigateTo, currentIndex]);

  const handleDownload = async () => {
    if (!photo || downloading) return;
    setDownloading(true);
    try {
      const blob = await guestFetchBlob(
        eventId,
        `/api/v1/events/${eventId}/photos/${photo.id}/download`
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = '';
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // silently fail — could add a toast notification in future
    } finally {
      setDownloading(false);
    }
  };

  if (!photo) return null;

  const canGoBack = currentIndex > 0;
  const canGoForward = currentIndex < photos.length - 1 || photos.length < total;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/90 flex flex-col"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 shrink-0">
        <span className="text-white/60 text-sm">
          {currentIndex + 1} / {total}
        </span>
        <div className="flex items-center gap-3">
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="text-sm font-medium text-white bg-white/20 hover:bg-white/30 disabled:opacity-50 px-4 py-1.5 rounded-full transition-colors"
          >
            {downloading ? 'Saving...' : 'Download'}
          </button>
          <button
            onClick={onClose}
            className="text-white/70 hover:text-white text-2xl leading-none px-2"
            aria-label="Close"
          >
            ×
          </button>
        </div>
      </div>

      {/* Image area */}
      <div className="flex-1 relative flex items-center justify-center min-h-0">
        {blobUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={blobUrl}
            alt=""
            className="max-w-full max-h-full object-contain select-none"
            draggable={false}
          />
        ) : (
          <div className="w-64 h-64 bg-white/10 animate-pulse rounded" />
        )}
        {photo.is_photographer_choice && (
          <span className="absolute top-4 left-4 text-yellow-400 text-sm bg-black/50 px-2 py-1 rounded">
            ✦ Photographer&apos;s Choice
          </span>
        )}
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between px-4 py-4 shrink-0">
        <button
          onClick={() => navigateTo(currentIndex - 1)}
          disabled={!canGoBack}
          className="text-white/70 hover:text-white disabled:opacity-30 text-3xl px-3 py-1 transition-colors"
          aria-label="Previous photo"
        >
          ‹
        </button>
        <button
          onClick={() => navigateTo(currentIndex + 1)}
          disabled={!canGoForward}
          className="text-white/70 hover:text-white disabled:opacity-30 text-3xl px-3 py-1 transition-colors"
          aria-label="Next photo"
        >
          ›
        </button>
      </div>
    </div>
  );
}

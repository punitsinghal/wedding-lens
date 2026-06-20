'use client';

import { useEffect, useState } from 'react';
import { guestFetchBlob } from '@/lib/api';
import type { GalleryPhoto } from '@/types/api';

interface PhotoThumbnailProps {
  photo: GalleryPhoto;
  eventId: string;
  onClick: () => void;
}

export default function PhotoThumbnail({ photo, eventId, onClick }: PhotoThumbnailProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!photo.thumbnail_url) return;

    let objectUrl: string | null = null;
    let cancelled = false;

    guestFetchBlob(eventId, `/api/v1/events/${eventId}/photos/${photo.id}/thumbnail`)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => {
        // leave blobUrl as null — placeholder stays visible
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [photo.id, photo.thumbnail_url, eventId]);

  return (
    <button
      onClick={onClick}
      className="relative aspect-square w-full overflow-hidden rounded-sm bg-gray-200 hover:opacity-90 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-900"
    >
      {blobUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={blobUrl}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 bg-gray-200 animate-pulse" />
      )}
      {photo.is_photographer_choice && (
        <span
          className="absolute top-1 right-1 text-xs leading-none bg-black/50 text-yellow-400 rounded px-1 py-0.5"
          aria-label="Photographer's choice"
        >
          ✦
        </span>
      )}
    </button>
  );
}

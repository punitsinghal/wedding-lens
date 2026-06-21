'use client';

import { useEffect, useState } from 'react';
import { guestFetchBlob } from '@/lib/api';
import type { GalleryPhoto } from '@/types/api';
import FavouriteToggle from '@/components/photo-actions/FavouriteToggle';
import ShareButton from '@/components/photo-actions/ShareButton';

interface PhotoThumbnailProps {
  photo: GalleryPhoto;
  eventId: string;
  onClick: () => void;
  isFavourited: boolean;
  onToggleFavourite: () => void;
}

export default function PhotoThumbnail({
  photo,
  eventId,
  onClick,
  isFavourited,
  onToggleFavourite,
}: PhotoThumbnailProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!photo.thumbnail_url) return;

    let objectUrl: string | null = null;
    let cancelled = false;

    guestFetchBlob(eventId, photo.thumbnail_url!)
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
    <div className="relative aspect-square w-full overflow-hidden rounded-sm bg-gray-200 group">
      <button
        onClick={onClick}
        className="absolute inset-0 w-full h-full hover:opacity-90 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-gray-900"
        aria-label="View photo"
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
      </button>
      {photo.is_photographer_choice && (
        <span
          className="absolute top-1 right-1 text-xs leading-none bg-black/50 text-yellow-400 rounded px-1 py-0.5 pointer-events-none"
          aria-label="Photographer's choice"
        >
          ✦
        </span>
      )}
      <div className="absolute bottom-1.5 right-1.5 flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
        <FavouriteToggle isFavourited={isFavourited} onToggle={onToggleFavourite} />
        <ShareButton eventId={eventId} photoId={photo.id} />
      </div>
    </div>
  );
}

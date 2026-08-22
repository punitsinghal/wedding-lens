'use client';

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
  return (
    <div className="relative aspect-square w-full overflow-hidden rounded-sm bg-gray-200 group">
      <button
        onClick={onClick}
        className="absolute inset-0 w-full h-full hover:opacity-90 transition-opacity focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-gray-900"
        aria-label="View photo"
      >
        {photo.thumbnail_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo.thumbnail_url}
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
      {photo.uploaded_by === 'guest' && (
        <span className="tag tag-neutral absolute bottom-1.5 left-1.5 max-w-[85%] truncate pointer-events-none">
          Guest photo · {photo.guest_display_name ?? 'Guest'}
        </span>
      )}
      <div className="absolute bottom-1.5 right-1.5 flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
        <FavouriteToggle isFavourited={isFavourited} onToggle={onToggleFavourite} />
        <ShareButton eventId={eventId} photoId={photo.id} />
      </div>
    </div>
  );
}

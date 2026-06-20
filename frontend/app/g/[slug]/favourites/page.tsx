'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { isGuestAuthenticated } from '@/lib/auth';
import { getEventBySlug, getFavourites, guestFetchBlob } from '@/lib/api';
import { useFavourites } from '@/hooks/useFavourites';
import FavouriteToggle from '@/components/photo-actions/FavouriteToggle';
import ShareButton from '@/components/photo-actions/ShareButton';
import BulkDownloadButton from '@/components/photo-actions/BulkDownloadButton';
import type { FavouritePhoto } from '@/types/api';

interface FavouriteCardProps {
  photo: FavouritePhoto;
  eventId: string;
  isFavourited: boolean;
  onToggle: () => void;
}

function FavouriteCard({ photo, eventId, isFavourited, onToggle }: FavouriteCardProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!photo.thumbnail_url) return;
    let objectUrl: string | null = null;
    let cancelled = false;
    guestFetchBlob(eventId, photo.thumbnail_url)
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
  }, [photo.photo_id, photo.thumbnail_url, eventId]);

  // Hide card immediately when unfavourited
  if (!isFavourited) return null;

  return (
    <div className="relative aspect-square w-full overflow-hidden rounded-sm bg-gray-200 group">
      {blobUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={blobUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />
      ) : (
        <div className="absolute inset-0 bg-gray-200 animate-pulse" />
      )}
      <div className="absolute bottom-1.5 right-1.5 flex gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
        <FavouriteToggle isFavourited={isFavourited} onToggle={onToggle} />
        <ShareButton eventId={eventId} photoId={photo.photo_id} />
      </div>
    </div>
  );
}

export default function FavouritesPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const [eventId, setEventId] = useState('');
  const [photos, setPhotos] = useState<FavouritePhoto[]>([]);
  const [isChecking, setIsChecking] = useState(true);

  const { isFavourited, toggle, favouriteIds } = useFavourites(eventId);

  useEffect(() => {
    getEventBySlug(slug)
      .then((ev) => {
        if (ev.access_mode !== 'public' && !isGuestAuthenticated(ev.id)) {
          router.replace(`/g/${slug}`);
          return;
        }
        setEventId(ev.id);
        return getFavourites(ev.id);
      })
      .then((res) => {
        if (res) setPhotos(res.photos);
      })
      .catch(() => {
        router.replace(`/g/${slug}`);
      })
      .finally(() => setIsChecking(false));
  }, [slug, router]);

  if (isChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  const visiblePhotos = photos.filter((p) => favouriteIds.has(p.photo_id));

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">My Favourites</h1>
            <Link href={`/g/${slug}/gallery`} className="text-sm text-blue-600 hover:underline mt-0.5 inline-block">
              Back to gallery
            </Link>
          </div>
          {visiblePhotos.length > 0 && (
            <BulkDownloadButton source="favourites" eventId={eventId} disabled={false} />
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-4">
        {visiblePhotos.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <svg className="h-12 w-12 text-gray-300 mb-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12Z" />
            </svg>
            <p className="text-gray-600 font-medium">No favourites yet</p>
            <p className="mt-1 text-sm text-gray-400">
              Tap the heart on any photo in your search results to save it here.
            </p>
            <Link
              href={`/g/${slug}/gallery`}
              className="mt-6 px-5 py-2 text-sm font-medium bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors"
            >
              Browse photos
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5">
            {photos.map((photo) => (
              <FavouriteCard
                key={photo.photo_id}
                photo={photo}
                eventId={eventId}
                isFavourited={isFavourited(photo.photo_id)}
                onToggle={() => toggle(photo.photo_id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

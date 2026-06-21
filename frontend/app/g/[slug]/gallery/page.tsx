'use client';

import { useState, useEffect, useRef, useCallback, Suspense } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getEventBySlug, getGalleryAlbums, getGalleryPhotos } from '@/lib/api';
import { isGuestAuthenticated } from '@/lib/auth';
import { useFavourites } from '@/hooks/useFavourites';
import AlbumFilterBar from '@/components/gallery/AlbumFilterBar';
import SortSelector from '@/components/gallery/SortSelector';
import PhotoThumbnail from '@/components/gallery/PhotoThumbnail';
import Lightbox from '@/components/gallery/Lightbox';
import type { EventPublicOut, GalleryPhoto, AlbumTab } from '@/types/api';

const PAGE_SIZE = 50;
const VALID_SORTS = ['latest', 'popular', 'photographer-choice'] as const;
type SortValue = (typeof VALID_SORTS)[number];

function isValidSort(v: string | null): v is SortValue {
  return VALID_SORTS.includes(v as SortValue);
}

// Inner component that uses useSearchParams (must be wrapped in Suspense)
function GalleryContent() {
  const router = useRouter();
  const params = useParams();
  const searchParams = useSearchParams();
  const slug = params.slug as string;

  const [event, setEvent] = useState<EventPublicOut | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [tabs, setTabs] = useState<AlbumTab[]>([]);
  const [activeAlbum, setActiveAlbum] = useState<string | null>(null);
  const [sort, setSort] = useState<SortValue>('latest');
  const [photos, setPhotos] = useState<GalleryPhoto[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);
  const savedScrollY = useRef(0);

  const { isFavourited, toggle: toggleFavourite, favouriteIds } = useFavourites(event?.id ?? '');

  // ---------------------------------------------------------------------------
  // Auth check + initial state from URL
  // ---------------------------------------------------------------------------
  useEffect(() => {
    getEventBySlug(slug)
      .then((ev) => {
        if (ev.access_mode !== 'public' && !isGuestAuthenticated(ev.id)) {
          router.replace(`/g/${slug}`);
          setIsChecking(false);
          return;
        }
        setEvent(ev);

        // Parse URL params
        const urlAlbum = searchParams.get('album');
        const urlSort = searchParams.get('sort');
        const urlLimit = parseInt(searchParams.get('limit') ?? '0', 10);

        const initialAlbum = urlAlbum ?? null;
        const initialSort: SortValue = isValidSort(urlSort) ? urlSort : 'latest';
        const initialLimit = urlLimit > 0 ? urlLimit : PAGE_SIZE;

        setActiveAlbum(initialAlbum);
        setSort(initialSort);

        // Load tabs and initial batch of photos
        const albumsPromise = getGalleryAlbums(ev.id);

        // Fetch all restore batches in parallel (faster than sequential for 2-3 batches;
        // the backend handles concurrent requests fine and the total volume is bounded
        // by the URL limit which guests set themselves).
        const batchCount = Math.ceil(initialLimit / PAGE_SIZE);
        const batches = Array.from({ length: batchCount }, (_, i) =>
          getGalleryPhotos(ev.id, {
            album: initialAlbum ?? undefined,
            sort: initialSort,
            limit: PAGE_SIZE,
            offset: i * PAGE_SIZE,
          })
        );

        setLoading(true);
        Promise.all([albumsPromise, Promise.all(batches)] as const)
          .then(([albumsResult, photoResults]) => {
            setTabs(albumsResult);
            const allPhotos: GalleryPhoto[] = [];
            let finalTotal = 0;
            for (const r of photoResults) {
              allPhotos.push(...r.photos);
              finalTotal = r.total;
            }
            setPhotos(allPhotos);
            setTotal(finalTotal);
          })
          .catch(() => {
            // If fetch fails, still show the page — photos will just be empty
          })
          .finally(() => {
            setLoading(false);
            setIsChecking(false);
          });
      })
      .catch(() => {
        router.replace(`/g/${slug}`);
        setIsChecking(false);
      });
    // Only run on mount — searchParams is stable via Next.js
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, router]);

  // ---------------------------------------------------------------------------
  // Sync URL when filter/sort/photos changes (after initial load)
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (!event) return;
    const qs = new URLSearchParams();
    if (activeAlbum) qs.set('album', activeAlbum);
    qs.set('sort', sort);
    if (photos.length > 0) qs.set('limit', String(photos.length));
    router.replace(`?${qs.toString()}`, { scroll: false });
  }, [activeAlbum, sort, photos.length, event, router]);

  // ---------------------------------------------------------------------------
  // Fetch photos for current filter/sort (resets list)
  // ---------------------------------------------------------------------------
  const fetchPhotos = useCallback(
    async (eventId: string, album: string | null, sortVal: SortValue) => {
      setLoading(true);
      try {
        const result = await getGalleryPhotos(eventId, {
          album: album ?? undefined,
          sort: sortVal,
          limit: PAGE_SIZE,
          offset: 0,
        });
        setPhotos(result.photos);
        setTotal(result.total);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const handleAlbumChange = useCallback(
    (cat: string | null) => {
      if (!event) return;
      setActiveAlbum(cat);
      setPhotos([]);
      fetchPhotos(event.id, cat, sort);
    },
    [event, sort, fetchPhotos]
  );

  const handleSortChange = useCallback(
    (val: string) => {
      if (!isValidSort(val) || !event) return;
      setSort(val);
      setPhotos([]);
      fetchPhotos(event.id, activeAlbum, val);
    },
    [event, activeAlbum, fetchPhotos]
  );

  // ---------------------------------------------------------------------------
  // Load more
  // ---------------------------------------------------------------------------
  const loadMore = useCallback(async () => {
    if (!event || loading) return;
    setLoading(true);
    try {
      const result = await getGalleryPhotos(event.id, {
        album: activeAlbum ?? undefined,
        sort,
        limit: PAGE_SIZE,
        offset: photos.length,
      });
      setPhotos((prev) => [...prev, ...result.photos]);
      setTotal(result.total);
    } finally {
      setLoading(false);
    }
  }, [event, loading, activeAlbum, sort, photos.length]);

  // ---------------------------------------------------------------------------
  // Lightbox
  // ---------------------------------------------------------------------------
  const openLightbox = (index: number) => {
    savedScrollY.current = window.scrollY;
    setLightboxIndex(index);
  };

  const closeLightbox = () => {
    setLightboxIndex(null);
    window.scrollTo(0, savedScrollY.current);
  };

  const handleLightboxNavigate = (newIndex: number) => {
    if (newIndex >= 0 && newIndex < photos.length) {
      setLightboxIndex(newIndex);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  if (isChecking || !event) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-gray-900">{event.name}</h1>
            <p className="text-sm text-gray-500 mt-0.5">
              {event.bride_name} &amp; {event.groom_name}
            </p>
          </div>
          <div className="flex gap-2 items-center">
            <Link
              href={`/g/${slug}/search`}
              className="px-3 py-1.5 text-sm font-medium bg-blue-600 text-white rounded-full hover:bg-blue-700 transition-colors"
            >
              Find my photos
            </Link>
            <Link
              href={`/g/${slug}/favourites`}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-200 rounded-full hover:bg-gray-50 transition-colors"
            >
              Favourites
              {favouriteIds.size > 0 && (
                <span className="text-xs bg-gray-100 text-gray-600 px-1.5 py-0.5 rounded-full ml-1">
                  {favouriteIds.size}
                </span>
              )}
            </Link>
          </div>
        </div>
      </header>

      {/* Filters */}
      <div className="bg-white border-b border-gray-200 px-4 py-3 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {tabs.length > 0 && (
            <AlbumFilterBar
              tabs={tabs}
              activeAlbum={activeAlbum}
              onChange={handleAlbumChange}
            />
          )}
          <div className="shrink-0">
            <SortSelector value={sort} onChange={handleSortChange} />
          </div>
        </div>
      </div>

      {/* Grid */}
      <main className="max-w-6xl mx-auto px-4 py-4">
        {photos.length === 0 && !loading ? (
          <div className="flex items-center justify-center py-24">
            <p className="text-gray-400 text-sm">No photos yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5">
            {photos.map((photo, index) => (
              <PhotoThumbnail
                key={photo.id}
                photo={photo}
                eventId={event.id}
                onClick={() => openLightbox(index)}
                isFavourited={isFavourited(photo.id)}
                onToggleFavourite={() => toggleFavourite(photo.id)}
              />
            ))}
            {/* Skeleton placeholders while loading */}
            {loading &&
              Array.from({ length: 10 }).map((_, i) => (
                <div
                  key={`skeleton-${i}`}
                  className="aspect-square bg-gray-200 animate-pulse rounded-sm"
                />
              ))}
          </div>
        )}

        {/* Load more */}
        {photos.length < total && (
          <div className="flex justify-center pt-6 pb-4">
            <button
              onClick={loadMore}
              disabled={loading}
              className="px-6 py-2 text-sm font-medium bg-gray-900 text-white rounded-full hover:bg-gray-700 disabled:opacity-50 transition-colors"
            >
              {loading ? 'Loading...' : 'Load more'}
            </button>
          </div>
        )}
      </main>

      {/* Lightbox */}
      {lightboxIndex !== null && (
        <Lightbox
          photos={photos}
          currentIndex={lightboxIndex}
          eventId={event.id}
          total={total}
          onClose={closeLightbox}
          onNavigate={handleLightboxNavigate}
          onFetchMore={loadMore}
          isFavourited={isFavourited(photos[lightboxIndex]?.id ?? '')}
          onToggleFavourite={() => toggleFavourite(photos[lightboxIndex]?.id ?? '')}
        />
      )}
    </div>
  );
}

export default function GuestGallery() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <p className="text-gray-400 text-sm">Loading...</p>
        </div>
      }
    >
      <GalleryContent />
    </Suspense>
  );
}

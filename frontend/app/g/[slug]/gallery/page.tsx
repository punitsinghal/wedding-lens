'use client';

import { useState, useEffect, useRef, useCallback, Suspense, FormEvent } from 'react';
import { useRouter, useParams, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { getEventBySlug, getGalleryAlbums, getGalleryPhotos, guestAuth, submitRemovalRequest } from '@/lib/api';
import { isGuestAuthenticated, setGuestToken } from '@/lib/auth';
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

  // S3: removal request form state
  const [showRemovalForm, setShowRemovalForm] = useState(false);
  const [removalName, setRemovalName] = useState('');
  const [removalEmail, setRemovalEmail] = useState('');
  const [removalDescription, setRemovalDescription] = useState('');
  const [removalNameError, setRemovalNameError] = useState('');
  const [removalEmailError, setRemovalEmailError] = useState('');
  const [removalDescriptionError, setRemovalDescriptionError] = useState('');
  const [removalSubmitting, setRemovalSubmitting] = useState(false);
  const [removalError, setRemovalError] = useState('');
  const [removalSuccess, setRemovalSuccess] = useState(false);

  const { isFavourited, toggle: toggleFavourite, favouriteIds } = useFavourites(event?.id ?? '');

  // ---------------------------------------------------------------------------
  // Auth check + initial state from URL
  // ---------------------------------------------------------------------------
  useEffect(() => {
    async function init() {
      let ev: EventPublicOut;
      try {
        ev = await getEventBySlug(slug);
      } catch {
        router.replace(`/g/${slug}`);
        setIsChecking(false);
        return;
      }

      if (ev.access_mode !== 'public' && !isGuestAuthenticated(ev.id)) {
        router.replace(`/g/${slug}`);
        setIsChecking(false);
        return;
      }

      // Public events skip the entry-page code form so no guest JWT is stored.
      // Always refresh the token for public events — isGuestAuthenticated only
      // checks expiry, not signature validity, so a stale token from a previous
      // backend instance would pass the client check but be rejected with 401.
      if (ev.access_mode === 'public') {
        try {
          const { access_token } = await guestAuth(ev.id, '');
          setGuestToken(ev.id, access_token);
        } catch {
          // If token issuance fails, continue — API calls will fail and show empty gallery
        }
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
      try {
        const [albumsResult, photoResults] = await Promise.all([
          albumsPromise,
          Promise.all(batches),
        ]);
        setTabs(albumsResult);
        const allPhotos: GalleryPhoto[] = [];
        let finalTotal = 0;
        for (const r of photoResults) {
          allPhotos.push(...r.photos);
          finalTotal = r.total;
        }
        setPhotos(allPhotos);
        setTotal(finalTotal);
      } catch {
        // If fetch fails, still show the page — photos will just be empty
      } finally {
        setLoading(false);
        setIsChecking(false);
      }
    }

    init();
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
  // S3: Removal request submission
  // ---------------------------------------------------------------------------
  async function handleRemovalSubmit(e: FormEvent) {
    e.preventDefault();
    setRemovalNameError('');
    setRemovalEmailError('');
    setRemovalDescriptionError('');
    setRemovalError('');

    let hasError = false;
    if (!removalName.trim()) {
      setRemovalNameError('Name is required.');
      hasError = true;
    }
    if (!removalEmail.trim()) {
      setRemovalEmailError('Email is required.');
      hasError = true;
    }
    if (!removalDescription.trim()) {
      setRemovalDescriptionError('Description is required.');
      hasError = true;
    }
    if (hasError) return;

    if (!event) return;
    setRemovalSubmitting(true);
    try {
      await submitRemovalRequest(event.id, {
        name: removalName.trim(),
        email: removalEmail.trim(),
        description: removalDescription.trim(),
      });
      setRemovalSuccess(true);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setRemovalError(apiErr?.detail ?? 'Failed to submit request. Please try again.');
    } finally {
      setRemovalSubmitting(false);
    }
  }

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
          <div className="flex gap-2 items-center flex-wrap justify-end">
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
            {/* S3: Remove my face data link (AC-3a) */}
            <button
              onClick={() => setShowRemovalForm(true)}
              className="px-3 py-1.5 text-sm font-medium text-red-600 bg-white border border-red-200 rounded-full hover:bg-red-50 transition-colors"
            >
              Remove my face data
            </button>
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

      {/* S3: Removal request modal */}
      {showRemovalForm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="removal-form-title"
        >
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 id="removal-form-title" className="text-base font-semibold text-gray-900">
                Remove my face data
              </h2>
              <button
                onClick={() => {
                  setShowRemovalForm(false);
                  setRemovalSuccess(false);
                  setRemovalName('');
                  setRemovalEmail('');
                  setRemovalDescription('');
                  setRemovalNameError('');
                  setRemovalEmailError('');
                  setRemovalDescriptionError('');
                  setRemovalError('');
                }}
                className="text-gray-400 hover:text-gray-600"
                aria-label="Close"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {removalSuccess ? (
              <div className="py-4 text-center">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-green-500 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <p className="text-sm font-medium text-gray-900 mb-1">Request received</p>
                <p className="text-sm text-gray-500">
                  Your face data removal request has been submitted. It will be processed within 24 hours.
                </p>
              </div>
            ) : (
              <form onSubmit={handleRemovalSubmit} noValidate className="space-y-4">
                <p className="text-sm text-gray-600">
                  Fill in this form to request removal of your face data from this event. All fields are required.
                </p>

                <div>
                  <label htmlFor="removal-name" className="block text-sm font-medium text-gray-700 mb-1">
                    Your name <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="removal-name"
                    type="text"
                    value={removalName}
                    onChange={(e) => { setRemovalName(e.target.value); setRemovalNameError(''); }}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="e.g. Priya Sharma"
                  />
                  {removalNameError && (
                    <p className="mt-1 text-xs text-red-600">{removalNameError}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="removal-email" className="block text-sm font-medium text-gray-700 mb-1">
                    Email address <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="removal-email"
                    type="email"
                    value={removalEmail}
                    onChange={(e) => { setRemovalEmail(e.target.value); setRemovalEmailError(''); }}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    placeholder="you@example.com"
                  />
                  {removalEmailError && (
                    <p className="mt-1 text-xs text-red-600">{removalEmailError}</p>
                  )}
                </div>

                <div>
                  <label htmlFor="removal-description" className="block text-sm font-medium text-gray-700 mb-1">
                    When did you upload a selfie? <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    id="removal-description"
                    value={removalDescription}
                    onChange={(e) => { setRemovalDescription(e.target.value); setRemovalDescriptionError(''); }}
                    rows={3}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                    placeholder="e.g. I uploaded a selfie on 15 June around 7 pm during the reception."
                  />
                  {removalDescriptionError && (
                    <p className="mt-1 text-xs text-red-600">{removalDescriptionError}</p>
                  )}
                </div>

                {removalError && (
                  <p className="text-sm text-red-600">{removalError}</p>
                )}

                <div className="flex justify-end gap-3 pt-1">
                  <button
                    type="button"
                    onClick={() => {
                      setShowRemovalForm(false);
                      setRemovalName('');
                      setRemovalEmail('');
                      setRemovalDescription('');
                      setRemovalNameError('');
                      setRemovalEmailError('');
                      setRemovalDescriptionError('');
                      setRemovalError('');
                    }}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={removalSubmitting}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {removalSubmitting ? 'Submitting...' : 'Submit request'}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
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

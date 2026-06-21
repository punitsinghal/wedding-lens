'use client';

import { useState, useEffect, useRef, useCallback, DragEvent, ChangeEvent } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import {
  getEvent,
  getAlbums,
  getPhotos,
  updatePhotoAlbum,
  ownerFetchBlob,
  hashFile,
  initiateUpload,
  uploadChunk,
  completeUpload,
  subscribeProgress,
  reprocessPhoto,
} from '@/lib/api';
import { isAuthenticated, getToken } from '@/lib/auth';
import type { Event, Album, Photo } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';

const LIMIT = 50;
// Accepted file types and size cap
const ACCEPTED_TYPES = ['image/jpeg', 'image/png'];
const MAX_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
// Files uploading concurrently
const CONCURRENCY = 3;
// Retry attempts per chunk on network error
const CHUNK_RETRIES = 3;
const CHUNK_RETRY_DELAY_MS = 1000;

type UploadStatus = 'queued' | 'hashing' | 'uploading' | 'done' | 'error' | 'duplicate';

interface UploadItem {
  id: string;
  file: File;
  status: UploadStatus;
  progress?: number; // 0–100 percent of chunks sent
  error?: string;
  sessionId?: string;
}

interface ProgressData {
  total: number;
  indexed: number;
  pending: number;
  failed: number;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function processingBadge(status: string) {
  const styles: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-600',
    processing: 'bg-blue-100 text-blue-700',
    complete: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
    error: 'bg-red-100 text-red-700',
  };
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded font-medium ${styles[status] ?? 'bg-gray-100 text-gray-600'}`}
    >
      {status}
    </span>
  );
}

function PhotoCard({
  photo,
  albums,
  eventId,
  onAlbumChange,
  onRetry,
}: {
  photo: Photo;
  albums: Album[];
  eventId: string;
  onAlbumChange: (photoId: string, albumId: string | null) => void;
  onRetry: (photoId: string) => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isChangingAlbum, setIsChangingAlbum] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  useEffect(() => {
    if (!photo.thumbnail_url) return;
    let objectUrl: string | null = null;
    let cancelled = false;

    ownerFetchBlob(photo.thumbnail_url)
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
  }, [photo.id, photo.thumbnail_url]);

  async function handleAlbumChange(e: ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    setIsChangingAlbum(true);
    try {
      await onAlbumChange(photo.id, val === '' ? null : val);
    } catch {
      // Revert select to the current album value
      (e.target as HTMLSelectElement).value = photo.album_id ?? '';
    } finally {
      setIsChangingAlbum(false);
    }
  }

  async function handleRetry() {
    setIsRetrying(true);
    try {
      await reprocessPhoto(eventId, photo.id);
      onRetry(photo.id);
    } catch {
      // silently ignore — user can try again
    } finally {
      setIsRetrying(false);
    }
  }

  const canRetry =
    photo.processing_status === 'failed' || photo.processing_status === 'error';

  return (
    <div className="border border-gray-200 rounded-md overflow-hidden bg-white">
      <div className="relative aspect-square bg-gray-100">
        {blobUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={blobUrl} alt="" className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <div className="absolute inset-0 bg-gray-200 animate-pulse" />
        )}
      </div>
      <div className="p-2 space-y-1.5">
        <p className="text-xs text-gray-700 truncate" title={photo.filename}>
          {photo.filename}
        </p>
        <div className="flex items-center gap-1.5 flex-wrap">
          {processingBadge(photo.processing_status)}
          {canRetry && (
            <button
              onClick={handleRetry}
              disabled={isRetrying}
              className="text-xs text-blue-600 hover:underline disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRetrying ? 'Retrying...' : 'Retry'}
            </button>
          )}
        </div>
        <select
          value={photo.album_id ?? ''}
          onChange={handleAlbumChange}
          disabled={isChangingAlbum}
          className="w-full text-xs border border-gray-300 rounded px-1.5 py-1 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        >
          <option value="">No album</option>
          {albums.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default function PhotosPage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.eventId as string;

  useEffect(() => {
    if (!isAuthenticated()) router.replace('/login');
  }, [router]);

  const [event, setEvent] = useState<Event | null>(null);
  const [albums, setAlbums] = useState<Album[]>([]);
  const [photos, setPhotos] = useState<Photo[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  // Upload state
  const [selectedAlbumId, setSelectedAlbumId] = useState<string>('');
  const [uploadQueue, setUploadQueue] = useState<UploadItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // SSE progress state
  const [progressData, setProgressData] = useState<ProgressData | null>(null);
  const [galleryReady, setGalleryReady] = useState(false);
  const [galleryBannerDismissed, setGalleryBannerDismissed] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---------------------------------------------------------------------------
  // SSE subscription
  // ---------------------------------------------------------------------------

  const openSSE = useCallback(() => {
    // Close existing connection if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }

    const token = getToken();
    if (!token) return;

    const es = subscribeProgress(eventId, token);
    eventSourceRef.current = es;

    es.addEventListener('progress', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as ProgressData;
        setProgressData(data);
      } catch {
        // ignore malformed events
      }
    });

    es.addEventListener('gallery_ready', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data as string) as ProgressData;
        setProgressData(data);
      } catch {
        // ignore malformed events
      }
      setGalleryReady(true);
    });

    es.onerror = () => {
      es.close();
      eventSourceRef.current = null;
      // Reconnect after 60 s
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        openSSE();
      }, 60_000);
    };
  }, [eventId]);

  useEffect(() => {
    openSSE();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [openSSE]);

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  useEffect(() => {
    Promise.all([getEvent(eventId), getAlbums(eventId)])
      .then(([ev, alb]) => {
        setEvent(ev);
        setAlbums(alb);
      })
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setLoadError(apiErr?.detail ?? 'Failed to load data.');
      });
  }, [eventId]);

  const loadPhotos = useCallback(
    async (newOffset: number) => {
      setIsLoading(true);
      try {
        const res = await getPhotos(eventId, { limit: LIMIT, offset: newOffset });
        setPhotos(res.items);
        setTotal(res.total);
        setOffset(newOffset);
      } catch (err: unknown) {
        const apiErr = err as { detail?: string };
        setLoadError(apiErr?.detail ?? 'Failed to load photos.');
      } finally {
        setIsLoading(false);
      }
    },
    [eventId]
  );

  useEffect(() => {
    loadPhotos(0);
  }, [loadPhotos]);

  // ---------------------------------------------------------------------------
  // File selection and validation
  // ---------------------------------------------------------------------------

  function addFiles(files: FileList | File[]) {
    const validItems: UploadItem[] = [];
    for (const f of Array.from(files)) {
      if (!ACCEPTED_TYPES.includes(f.type)) continue;
      if (f.size > MAX_SIZE_BYTES) {
        // Show inline error — add as an error item so the user sees the rejection
        validItems.push({
          id: `${f.name}-${f.size}-${f.lastModified}`,
          file: f,
          status: 'error',
          error: 'File exceeds 25 MB limit',
        });
        continue;
      }
      validItems.push({
        id: `${f.name}-${f.size}-${f.lastModified}`,
        file: f,
        status: 'queued',
      });
    }
    setUploadQueue((prev) => [...prev, ...validItems]);
  }

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
  }

  function handleFileInput(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = '';
  }

  // ---------------------------------------------------------------------------
  // Chunked upload orchestrator
  // ---------------------------------------------------------------------------

  function updateItem(id: string, patch: Partial<UploadItem>) {
    setUploadQueue((prev) =>
      prev.map((item) => (item.id === id ? { ...item, ...patch } : item))
    );
  }

  async function uploadFile(item: UploadItem, albumId?: string | null): Promise<void> {
    const { id, file } = item;

    // 1. Hash
    updateItem(id, { status: 'hashing' });
    let hash: string;
    try {
      hash = await hashFile(file);
    } catch {
      updateItem(id, { status: 'error', error: 'Hash computation failed' });
      return;
    }

    // 2. Initiate session
    let sessionId: string;
    let chunkSizeBytes: number;
    let totalChunks: number;
    let receivedChunks: number[] = [];

    updateItem(id, { status: 'uploading' });
    try {
      const result = await initiateUpload(eventId, file.name, file.size, hash);
      if (result.type === 'duplicate') {
        updateItem(id, { status: 'duplicate', progress: 100 });
        return;
      }
      sessionId = result.session_id;
      chunkSizeBytes = result.chunk_size_bytes;
      totalChunks = result.total_chunks;
      if (result.type === 'resumable') {
        receivedChunks = result.received_chunks;
      }
      updateItem(id, { sessionId });
    } catch {
      updateItem(id, { status: 'error', error: 'Failed to start upload session' });
      return;
    }

    // 3. Upload missing chunks sequentially
    const receivedSet = new Set(receivedChunks);
    let sentCount = receivedChunks.length;

    for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex++) {
      if (receivedSet.has(chunkIndex)) continue;

      const start = chunkIndex * chunkSizeBytes;
      const end = Math.min(start + chunkSizeBytes, file.size);
      const slice = file.slice(start, end);
      const bytes = new Uint8Array(await slice.arrayBuffer());

      let lastError: unknown;
      let success = false;
      for (let attempt = 0; attempt < CHUNK_RETRIES; attempt++) {
        try {
          await uploadChunk(eventId, sessionId, chunkIndex, bytes);
          success = true;
          break;
        } catch (err) {
          lastError = err;
          if (attempt < CHUNK_RETRIES - 1) {
            await sleep(CHUNK_RETRY_DELAY_MS);
          }
        }
      }

      if (!success) {
        const errMsg =
          (lastError as { detail?: string })?.detail ?? 'Chunk upload failed';
        updateItem(id, { status: 'error', error: errMsg });
        return;
      }

      sentCount++;
      const progress = Math.round((sentCount / totalChunks) * 100);
      updateItem(id, { progress });
    }

    // 4. Complete
    try {
      await completeUpload(eventId, sessionId, albumId);
      updateItem(id, { status: 'done', progress: 100 });
    } catch {
      updateItem(id, { status: 'error', error: 'Failed to finalize upload' });
    }
  }

  async function handleUpload() {
    if (isUploading) return;
    const queued = uploadQueue.filter((item) => item.status === 'queued');
    if (queued.length === 0) return;

    setIsUploading(true);

    // Process files in batches of CONCURRENCY
    const albumId = selectedAlbumId || null;
    for (let i = 0; i < queued.length; i += CONCURRENCY) {
      const batch = queued.slice(i, i + CONCURRENCY);
      await Promise.all(batch.map((item) => uploadFile(item, albumId)));
    }

    setIsUploading(false);
    // Refresh photo grid
    await loadPhotos(0);
    // Clear done/duplicate items, keep errors so user can see what failed
    setUploadQueue((prev) =>
      prev.filter((item) => item.status === 'error')
    );
  }

  // ---------------------------------------------------------------------------
  // Album change (existing single-select flow)
  // ---------------------------------------------------------------------------

  async function handleAlbumChange(photoId: string, albumId: string | null) {
    try {
      const updated = await updatePhotoAlbum(eventId, photoId, albumId);
      setPhotos((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    } catch {
      // error surfaces via PhotoCard's select revert; no additional UI needed
    }
  }

  // ---------------------------------------------------------------------------
  // Reprocess retry from photo grid
  // ---------------------------------------------------------------------------

  function handleRetry(photoId: string) {
    setPhotos((prev) =>
      prev.map((p) => (p.id === photoId ? { ...p, processing_status: 'pending' } : p))
    );
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (loadError && !event) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {loadError}
        </div>
        <Link href="/dashboard" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const totalPages = Math.ceil(total / LIMIT);
  const currentPage = Math.floor(offset / LIMIT) + 1;
  const queuedCount = uploadQueue.filter((i) => i.status === 'queued').length;

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 mb-6 text-sm flex-wrap">
        <Link href="/dashboard" className="text-gray-500 hover:text-gray-700">
          Dashboard
        </Link>
        <span className="text-gray-300">/</span>
        <Link href={`/events/${eventId}`} className="text-gray-500 hover:text-gray-700 truncate">
          {event?.name ?? '...'}
        </Link>
        <span className="text-gray-300">/</span>
        <span className="text-gray-900 font-medium">Photos</span>
        {event && <StatusBadge status={event.status} />}
      </div>

      {/* Upload section */}
      <div className="mb-6 border border-gray-200 rounded-lg p-5 bg-white">
        <h2 className="text-sm font-semibold text-gray-800 mb-4">Upload Photos</h2>

        {/* Drop zone */}
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-md p-8 text-center cursor-pointer transition-colors ${
            isDragging
              ? 'border-blue-400 bg-blue-50'
              : 'border-gray-300 hover:border-gray-400 bg-gray-50'
          }`}
        >
          <p className="text-sm text-gray-500">
            Drag &amp; drop photos here, or{' '}
            <span className="text-blue-600 underline">browse</span>
          </p>
          <p className="text-xs text-gray-400 mt-1">JPEG and PNG only, max 25 MB each</p>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/jpeg,image/png"
            className="hidden"
            onChange={handleFileInput}
          />
        </div>

        {/* Album selector + upload button */}
        <div className="mt-4 flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <label className="text-sm text-gray-600 whitespace-nowrap">Album:</label>
            <select
              value={selectedAlbumId}
              onChange={(e) => setSelectedAlbumId(e.target.value)}
              className="border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">No album</option>
              {albums.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleUpload}
            disabled={isUploading || queuedCount === 0}
            className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isUploading
              ? 'Uploading...'
              : queuedCount > 0
              ? `Upload ${queuedCount} photo${queuedCount > 1 ? 's' : ''}`
              : 'Upload'}
          </button>

          {uploadQueue.length > 0 && !isUploading && (
            <button
              onClick={() => setUploadQueue([])}
              className="text-sm text-gray-400 hover:text-gray-600"
            >
              Clear
            </button>
          )}
        </div>

        {/* Upload queue */}
        {uploadQueue.length > 0 && (
          <div className="mt-3 space-y-1.5 max-h-48 overflow-y-auto">
            {uploadQueue.map((item) => (
              <div key={item.id} className="space-y-0.5">
                <div className="flex items-center gap-2 text-xs text-gray-600">
                  <span
                    className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      item.status === 'queued'
                        ? 'bg-gray-300'
                        : item.status === 'hashing'
                        ? 'bg-yellow-400 animate-pulse'
                        : item.status === 'uploading'
                        ? 'bg-blue-400 animate-pulse'
                        : item.status === 'done' || item.status === 'duplicate'
                        ? 'bg-green-400'
                        : 'bg-red-400'
                    }`}
                  />
                  <span className="truncate flex-1">{item.file.name}</span>
                  <span className="text-gray-400 flex-shrink-0">
                    {(item.file.size / 1024 / 1024).toFixed(1)} MB
                  </span>
                  {item.status === 'duplicate' && (
                    <span className="text-gray-400 flex-shrink-0">duplicate</span>
                  )}
                  {item.status === 'error' && (
                    <span className="text-red-500 flex-shrink-0">{item.error}</span>
                  )}
                  {item.status === 'uploading' && item.progress !== undefined && (
                    <span className="text-blue-500 flex-shrink-0 tabular-nums">
                      {item.progress}%
                    </span>
                  )}
                </div>
                {/* Progress bar */}
                {item.status === 'uploading' && item.progress !== undefined && (
                  <div className="ml-4 h-1 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all duration-200"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Processing status panel (SSE) */}
      <div className="mb-6 border border-gray-200 rounded-lg p-5 bg-white">
        <h2 className="text-sm font-semibold text-gray-800 mb-3">Processing Status</h2>

        {/* Gallery ready banner */}
        {galleryReady && !galleryBannerDismissed && (
          <div className="mb-3 flex items-center justify-between gap-3 px-4 py-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-sm font-medium text-green-800">
              Gallery ready &mdash; guests can now search!
            </p>
            <button
              onClick={() => setGalleryBannerDismissed(true)}
              className="text-green-600 hover:text-green-800 text-xs font-medium"
            >
              Dismiss
            </button>
          </div>
        )}

        {progressData ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="rounded-md border border-gray-100 bg-gray-50 p-3 text-center">
              <p className="text-xl font-semibold text-gray-800 tabular-nums">
                {progressData.total}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Total</p>
            </div>
            <div className="rounded-md border border-green-100 bg-green-50 p-3 text-center">
              <p className="text-xl font-semibold text-green-700 tabular-nums">
                {progressData.indexed}
              </p>
              <p className="text-xs text-green-600 mt-0.5">Indexed</p>
            </div>
            <div className="rounded-md border border-gray-100 bg-gray-50 p-3 text-center">
              <p className="text-xl font-semibold text-gray-600 tabular-nums">
                {progressData.pending}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">Pending</p>
            </div>
            <div className="rounded-md border border-red-100 bg-red-50 p-3 text-center">
              <p className="text-xl font-semibold text-red-700 tabular-nums">
                {progressData.failed}
              </p>
              <p className="text-xs text-red-500 mt-0.5">Failed</p>
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-400">Connecting to progress stream&hellip;</p>
        )}

        {progressData && progressData.failed > 0 && (
          <p className="mt-2 text-xs text-gray-500">
            {progressData.failed} photo{progressData.failed !== 1 ? 's' : ''} failed face
            processing. See photo grid below for retry options.
          </p>
        )}
      </div>

      {/* Photos grid */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-gray-800">
            {isLoading ? 'Loading...' : `${total} photo${total !== 1 ? 's' : ''}`}
          </h2>
        </div>

        {isLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="border border-gray-200 rounded-md overflow-hidden">
                <div className="aspect-square bg-gray-200 animate-pulse" />
                <div className="p-2 space-y-1.5">
                  <div className="h-3 bg-gray-200 rounded animate-pulse" />
                  <div className="h-3 w-16 bg-gray-200 rounded animate-pulse" />
                  <div className="h-6 bg-gray-200 rounded animate-pulse" />
                </div>
              </div>
            ))}
          </div>
        ) : photos.length === 0 ? (
          <div className="text-center py-12 text-sm text-gray-400">
            No photos yet. Upload some above.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
            {photos.map((photo) => (
              <PhotoCard
                key={photo.id}
                photo={photo}
                albums={albums}
                eventId={eventId}
                onAlbumChange={handleAlbumChange}
                onRetry={handleRetry}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => loadPhotos(offset - LIMIT)}
              disabled={offset === 0}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <span className="text-sm text-gray-500">
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => loadPhotos(offset + LIMIT)}
              disabled={offset + LIMIT >= total}
              className="px-3 py-1.5 text-sm border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

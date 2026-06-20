'use client';

import { useState, useEffect, useRef, useCallback, DragEvent, ChangeEvent } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getEvent, getAlbums, getPhotos, uploadPhoto, updatePhotoAlbum, ownerFetchBlob } from '@/lib/api';
import { isAuthenticated } from '@/lib/auth';
import type { Event, Album, Photo } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';

const LIMIT = 50;

type UploadStatus = 'queued' | 'uploading' | 'done' | 'error';

interface UploadItem {
  id: string;
  file: File;
  status: UploadStatus;
  error?: string;
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
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${styles[status] ?? 'bg-gray-100 text-gray-600'}`}>
      {status}
    </span>
  );
}

function PhotoCard({
  photo,
  albums,
  onAlbumChange,
}: {
  photo: Photo;
  albums: Album[];
  onAlbumChange: (photoId: string, albumId: string | null) => void;
}) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [isChangingAlbum, setIsChangingAlbum] = useState(false);

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
        {processingBadge(photo.processing_status)}
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

  function addFiles(files: FileList | File[]) {
    const arr = Array.from(files).filter(
      (f) => f.type === 'image/jpeg' || f.type === 'image/png'
    );
    setUploadQueue((prev) => [
      ...prev,
      ...arr.map((f) => ({
        id: `${f.name}-${f.size}-${f.lastModified}`,
        file: f,
        status: 'queued' as UploadStatus,
      })),
    ]);
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

  async function handleUpload() {
    if (isUploading || uploadQueue.length === 0) return;
    setIsUploading(true);

    for (let i = 0; i < uploadQueue.length; i++) {
      setUploadQueue((prev) =>
        prev.map((item, idx) => (idx === i ? { ...item, status: 'uploading' } : item))
      );
      try {
        await uploadPhoto(eventId, uploadQueue[i].file, selectedAlbumId || null);
        setUploadQueue((prev) =>
          prev.map((item, idx) => (idx === i ? { ...item, status: 'done' } : item))
        );
      } catch {
        setUploadQueue((prev) =>
          prev.map((item, idx) =>
            idx === i ? { ...item, status: 'error', error: 'Upload failed' } : item
          )
        );
      }
    }

    setIsUploading(false);
    // Refresh photo grid
    await loadPhotos(0);
    // Clear done items
    setUploadQueue((prev) => prev.filter((item) => item.status === 'error'));
  }

  async function handleAlbumChange(photoId: string, albumId: string | null) {
    try {
      const updated = await updatePhotoAlbum(eventId, photoId, albumId);
      setPhotos((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
    } catch {
      // error surfaces via PhotoCard's select revert; no additional UI needed
    }
  }

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
      <div className="mb-8 border border-gray-200 rounded-lg p-5 bg-white">
        <h2 className="text-sm font-semibold text-gray-800 mb-4">Upload Photos</h2>

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-md p-8 text-center cursor-pointer transition-colors ${
            isDragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'
          }`}
        >
          <p className="text-sm text-gray-500">
            Drag & drop photos here, or <span className="text-blue-600 underline">browse</span>
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
            disabled={isUploading || uploadQueue.length === 0}
            className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isUploading
              ? 'Uploading...'
              : uploadQueue.length > 0
              ? `Upload ${uploadQueue.length} photo${uploadQueue.length > 1 ? 's' : ''}`
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
          <div className="mt-3 space-y-1 max-h-40 overflow-y-auto">
            {uploadQueue.map((item) => (
              <div key={item.id} className="flex items-center gap-2 text-xs text-gray-600">
                <span
                  className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    item.status === 'queued'
                      ? 'bg-gray-300'
                      : item.status === 'uploading'
                      ? 'bg-blue-400 animate-pulse'
                      : item.status === 'done'
                      ? 'bg-green-400'
                      : 'bg-red-400'
                  }`}
                />
                <span className="truncate flex-1">{item.file.name}</span>
                <span className="text-gray-400 flex-shrink-0">
                  {(item.file.size / 1024 / 1024).toFixed(1)} MB
                </span>
                {item.status === 'error' && (
                  <span className="text-red-500 flex-shrink-0">{item.error}</span>
                )}
              </div>
            ))}
          </div>
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
                onAlbumChange={handleAlbumChange}
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

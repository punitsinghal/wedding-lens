// Typed fetch wrapper + auth header injection
// All API calls go through this module — never call fetch directly from components

import { getToken, getGuestToken, setGuestToken, clearGuestToken } from './auth';
export { getToken as getAuthToken };
import type {
  AuthResponse,
  Event,
  EventCreateRequest,
  EventUpdateRequest,
  EventPublicOut,
  GuestTokenOut,
  Album,
  AlbumCreateRequest,
  AlbumUpdateRequest,
  AdminEventsResponse,
  AlbumTab,
  GalleryListResponse,
  Photo,
  PhotoListResponse,
  PhotoUploadResponse,
  ShareLinkResponse,
  FavouritesResponse,
  ShareTokenResponse,
} from '@/types/api';

function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
}

interface FetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

async function apiFetch<T>(path: string, options: FetchOptions = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const init: RequestInit = {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  };

  const response = await fetch(`${baseUrl()}${path}`, init);

  if (!response.ok) {
    let errorBody: unknown;
    try {
      errorBody = await response.json();
    } catch {
      errorBody = { detail: response.statusText };
    }
    // Re-throw the parsed body so callers can inspect detail / suggestions
    throw errorBody;
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export async function fetchAuthedBlob(path: string): Promise<string> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(`${baseUrl()}${path}`, { headers });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function guestApiFetch<T>(
  eventId: string,
  path: string,
  options: FetchOptions = {}
): Promise<T> {
  const token = getGuestToken(eventId);
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const init: RequestInit = {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  };

  const response = await fetch(`${baseUrl()}${path}`, init);

  if (!response.ok) {
    if (response.status === 401) {
      clearGuestToken(eventId);
    }
    let errorBody: unknown;
    try {
      errorBody = await response.json();
    } catch {
      errorBody = { detail: response.statusText };
    }
    throw errorBody;
  }

  const freshToken = response.headers.get('X-Guest-Token');
  if (freshToken) {
    setGuestToken(eventId, freshToken);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function register(email: string, password: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>('/api/v1/auth/register', {
    method: 'POST',
    body: { email, password },
  });
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  return apiFetch<AuthResponse>('/api/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  });
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

export async function createEvent(data: EventCreateRequest): Promise<Event> {
  return apiFetch<Event>('/api/v1/events', {
    method: 'POST',
    body: data,
  });
}

export async function getEvent(eventId: string): Promise<Event> {
  return apiFetch<Event>(`/api/v1/events/${eventId}`);
}

export async function updateEvent(eventId: string, data: EventUpdateRequest): Promise<Event> {
  return apiFetch<Event>(`/api/v1/events/${eventId}`, {
    method: 'PUT',
    body: data,
  });
}

export async function deleteEvent(eventId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/events/${eventId}`, {
    method: 'DELETE',
  });
}

export async function publishEvent(eventId: string): Promise<Event> {
  return apiFetch<Event>(`/api/v1/events/${eventId}/publish`, {
    method: 'POST',
  });
}

export async function unpublishEvent(eventId: string): Promise<Event> {
  return apiFetch<Event>(`/api/v1/events/${eventId}/unpublish`, {
    method: 'POST',
  });
}

// QR code is proxied via Next.js API route to avoid CORS
export function getQrCodeUrl(eventId: string): string {
  return `/api/events/${eventId}/qr-code`;
}

// ---------------------------------------------------------------------------
// Albums
// ---------------------------------------------------------------------------

export async function getAlbums(eventId: string): Promise<Album[]> {
  return apiFetch<Album[]>(`/api/v1/events/${eventId}/albums`);
}

export async function getAlbum(eventId: string, albumId: string): Promise<Album> {
  return apiFetch<Album>(`/api/v1/events/${eventId}/albums/${albumId}`);
}

export async function createAlbum(eventId: string, data: AlbumCreateRequest): Promise<Album> {
  return apiFetch<Album>(`/api/v1/events/${eventId}/albums`, {
    method: 'POST',
    body: data,
  });
}

export async function updateAlbum(
  eventId: string,
  albumId: string,
  data: AlbumUpdateRequest
): Promise<Album> {
  return apiFetch<Album>(`/api/v1/events/${eventId}/albums/${albumId}`, {
    method: 'PUT',
    body: data,
  });
}

export async function deleteAlbum(eventId: string, albumId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/events/${eventId}/albums/${albumId}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export async function adminGetEvents(
  page: number = 1,
  pageSize: number = 20
): Promise<AdminEventsResponse> {
  return apiFetch<AdminEventsResponse>(
    `/api/v1/admin/events?page=${page}&page_size=${pageSize}`
  );
}

export async function adminSuspendEvent(eventId: string): Promise<Event> {
  return apiFetch<Event>(`/api/v1/admin/events/${eventId}/suspend`, {
    method: 'POST',
  });
}

export async function adminUnsuspendEvent(eventId: string): Promise<Event> {
  return apiFetch<Event>(`/api/v1/admin/events/${eventId}/unsuspend`, {
    method: 'POST',
  });
}

export async function adminDeleteEvent(eventId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/admin/events/${eventId}`, {
    method: 'DELETE',
  });
}

// ---------------------------------------------------------------------------
// Dashboard (owner's own events — reuses event endpoint patterns)
// ---------------------------------------------------------------------------

export async function getDashboardEvents(): Promise<Event[]> {
  return apiFetch<Event[]>('/api/v1/events');
}

// ---------------------------------------------------------------------------
// Guest access — public endpoints, no owner token required
// ---------------------------------------------------------------------------

export async function getEventBySlug(slug: string): Promise<EventPublicOut> {
  return apiFetch<EventPublicOut>(`/api/v1/events/by-slug/${slug}`);
}

export async function guestAuth(eventId: string, code: string): Promise<GuestTokenOut> {
  return apiFetch<GuestTokenOut>(`/api/v1/events/${eventId}/guest-auth`, {
    method: 'POST',
    body: { code },
  });
}

// ---------------------------------------------------------------------------
// Gallery — guest-authenticated endpoints
// ---------------------------------------------------------------------------

export async function guestFetchBlob(eventId: string, path: string): Promise<Blob> {
  const token = getGuestToken(eventId);
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(`${baseUrl()}${path}`, { headers });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const refreshed = response.headers.get('X-Guest-Token');
  if (refreshed) setGuestToken(eventId, refreshed);
  return response.blob();
}

export async function getGalleryAlbums(eventId: string): Promise<AlbumTab[]> {
  return guestApiFetch<AlbumTab[]>(eventId, `/api/v1/events/${eventId}/gallery/albums`);
}

export async function getGalleryPhotos(
  eventId: string,
  params: { album?: string; sort?: string; limit?: number; offset?: number }
): Promise<GalleryListResponse> {
  const qs = new URLSearchParams();
  if (params.album != null) qs.set('album', params.album);
  if (params.sort != null) qs.set('sort', params.sort);
  if (params.limit != null) qs.set('limit', String(params.limit));
  if (params.offset != null) qs.set('offset', String(params.offset));
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return guestApiFetch<GalleryListResponse>(
    eventId,
    `/api/v1/events/${eventId}/gallery${query}`
  );
}

// ---------------------------------------------------------------------------
// Guest access controls — owner-only endpoints
// ---------------------------------------------------------------------------

export async function revokeGuestAccess(eventId: string): Promise<{ detail: string }> {
  return apiFetch<{ detail: string }>(`/api/v1/events/${eventId}/revoke-guest-access`, {
    method: 'POST',
  });
}

export async function enableGuestAccess(eventId: string): Promise<{ detail: string }> {
  return apiFetch<{ detail: string }>(`/api/v1/events/${eventId}/enable-guest-access`, {
    method: 'POST',
  });
}

// ---------------------------------------------------------------------------
// Photos — owner-only endpoints
// ---------------------------------------------------------------------------

export async function uploadPhoto(
  eventId: string,
  file: File,
  albumId?: string | null
): Promise<PhotoUploadResponse> {
  const token = getToken();
  const formData = new FormData();
  formData.append('file', file);
  if (albumId) formData.append('album_id', albumId);

  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${baseUrl()}/api/v1/events/${eventId}/photos`, {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!response.ok) {
    let errorBody: unknown;
    try { errorBody = await response.json(); } catch { errorBody = { detail: response.statusText }; }
    throw errorBody;
  }

  return response.json() as Promise<PhotoUploadResponse>;
}

export async function getPhotos(
  eventId: string,
  params: { limit?: number; offset?: number; albumId?: string } = {}
): Promise<PhotoListResponse> {
  const qs = new URLSearchParams();
  if (params.limit != null) qs.set('limit', String(params.limit));
  if (params.offset != null) qs.set('offset', String(params.offset));
  if (params.albumId != null) qs.set('album_id', params.albumId);
  const query = qs.toString() ? `?${qs.toString()}` : '';
  return apiFetch<PhotoListResponse>(`/api/v1/events/${eventId}/photos${query}`);
}

export async function updatePhotoAlbum(
  eventId: string,
  photoId: string,
  albumId: string | null
): Promise<Photo> {
  return apiFetch<Photo>(`/api/v1/events/${eventId}/photos/${photoId}/album`, {
    method: 'PATCH',
    body: { album_id: albumId },
  });
}

export async function ownerFetchBlob(path: string): Promise<Blob> {
  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const response = await fetch(`${baseUrl()}${path}`, { headers });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.blob();
}

// ---------------------------------------------------------------------------
// Photo actions — guest-authenticated
// ---------------------------------------------------------------------------

export async function generateShareLink(
  eventId: string,
  photoId: string
): Promise<ShareLinkResponse> {
  return guestApiFetch<ShareLinkResponse>(
    eventId,
    `/api/v1/events/${eventId}/photos/${photoId}/share`,
    { method: 'POST' }
  );
}

export async function getFavourites(eventId: string): Promise<FavouritesResponse> {
  return guestApiFetch<FavouritesResponse>(eventId, `/api/v1/events/${eventId}/favourites`);
}

export async function addFavourite(eventId: string, photoId: string): Promise<void> {
  return guestApiFetch<void>(eventId, `/api/v1/events/${eventId}/favourites/${photoId}`, {
    method: 'PUT',
  });
}

export async function removeFavourite(eventId: string, photoId: string): Promise<void> {
  return guestApiFetch<void>(eventId, `/api/v1/events/${eventId}/favourites/${photoId}`, {
    method: 'DELETE',
  });
}

export async function resolveShareToken(token: string): Promise<ShareTokenResponse> {
  // Public endpoint — no guest auth
  const response = await fetch(`${baseUrl()}/api/v1/share/${token}`);
  if (!response.ok) {
    let errorBody: unknown;
    try { errorBody = await response.json(); } catch { errorBody = { detail: response.statusText }; }
    throw errorBody;
  }
  return response.json() as Promise<ShareTokenResponse>;
}

export async function downloadZip(eventId: string, photoIds: string[]): Promise<void> {
  const token = getGuestToken(eventId);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${baseUrl()}/api/v1/events/${eventId}/photos/zip`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ photo_ids: photoIds }),
  });

  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const freshToken = response.headers.get('X-Guest-Token');
  if (freshToken) setGuestToken(eventId, freshToken);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = response.headers.get('Content-Disposition')?.match(/filename="(.+?)"/)?.[1]
    ?? 'wedding-my-photos.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function downloadPhoto(eventId: string, photoId: string): Promise<void> {
  const token = getGuestToken(eventId);
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(
    `${baseUrl()}/api/v1/events/${eventId}/photos/${photoId}/download`,
    { headers }
  );
  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const freshToken = response.headers.get('X-Guest-Token');
  if (freshToken) setGuestToken(eventId, freshToken);

  const blob = await response.blob();
  const filename =
    response.headers.get('Content-Disposition')?.match(/filename="(.+?)"/)?.[1] ?? 'photo.jpg';
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Chunked upload — photographer-only
// ---------------------------------------------------------------------------

export async function hashFile(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
}

type InitiateUploadResult =
  | { type: 'new'; session_id: string; chunk_size_bytes: number; total_chunks: number }
  | { type: 'duplicate'; photo_id: string }
  | { type: 'resumable'; session_id: string; chunk_size_bytes: number; total_chunks: number; received_chunks: number[] };

export async function initiateUpload(
  eventId: string,
  filename: string,
  fileSizeBytes: number,
  contentHash: string
): Promise<InitiateUploadResult> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${baseUrl()}/api/v1/events/${eventId}/uploads`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ filename, file_size_bytes: fileSizeBytes, content_hash: contentHash }),
  });

  if (!response.ok) {
    let errorBody: unknown;
    try { errorBody = await response.json(); } catch { errorBody = { detail: response.statusText }; }
    throw errorBody;
  }

  const data = await response.json() as Record<string, unknown>;

  if (response.status === 200) {
    if ('status' in data && data.status === 'duplicate') {
      return { type: 'duplicate', photo_id: data.photo_id as string };
    }
    // resumable
    return {
      type: 'resumable',
      session_id: data.session_id as string,
      chunk_size_bytes: data.chunk_size_bytes as number,
      total_chunks: data.total_chunks as number,
      received_chunks: data.received_chunks as number[],
    };
  }

  // 201 — new session
  return {
    type: 'new',
    session_id: data.session_id as string,
    chunk_size_bytes: data.chunk_size_bytes as number,
    total_chunks: data.total_chunks as number,
  };
}

export async function getUploadSession(
  eventId: string,
  sessionId: string
): Promise<{ session_id: string; received_chunks: number[]; total_chunks: number; status: string }> {
  return apiFetch(`/api/v1/events/${eventId}/uploads/${sessionId}`);
}

export async function uploadChunk(
  eventId: string,
  sessionId: string,
  chunkIndex: number,
  bytes: Uint8Array
): Promise<void> {
  const token = getToken();
  const headers: Record<string, string> = { 'Content-Type': 'application/octet-stream' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(
    `${baseUrl()}/api/v1/events/${eventId}/uploads/${sessionId}/chunks/${chunkIndex}`,
    { method: 'PUT', headers, body: bytes.buffer as ArrayBuffer }
  );

  if (!response.ok) {
    let errorBody: unknown;
    try { errorBody = await response.json(); } catch { errorBody = { detail: response.statusText }; }
    throw errorBody;
  }
}

export async function completeUpload(
  eventId: string,
  sessionId: string
): Promise<{ photo_id: string }> {
  return apiFetch(`/api/v1/events/${eventId}/uploads/${sessionId}/complete`, { method: 'POST' });
}

// SSE progress — caller must close the returned EventSource when done
export function subscribeProgress(eventId: string, token: string): EventSource {
  const url = `${baseUrl()}/api/v1/events/${eventId}/progress?token=${encodeURIComponent(token)}`;
  return new EventSource(url);
}

export async function assignPhotoAlbums(
  eventId: string,
  photoId: string,
  albumIds: string[]
): Promise<void> {
  return apiFetch(`/api/v1/events/${eventId}/photos/${photoId}/albums`, {
    method: 'PUT',
    body: { album_ids: albumIds },
  });
}

export async function reprocessPhoto(eventId: string, photoId: string): Promise<void> {
  return apiFetch(`/api/v1/events/${eventId}/photos/${photoId}/reprocess`, { method: 'POST' });
}

// ---------------------------------------------------------------------------
// Photographer assignment
// ---------------------------------------------------------------------------

export async function assignPhotographer(
  eventId: string,
  email: string
): Promise<{ photographer_id: string; email: string }> {
  return apiFetch(`/api/v1/events/${eventId}/photographers`, {
    method: 'POST',
    body: { email },
  });
}

export async function removePhotographer(
  eventId: string,
  photographerId: string
): Promise<void> {
  return apiFetch(`/api/v1/events/${eventId}/photographers/${photographerId}`, {
    method: 'DELETE',
  });
}

export async function getMyAssignedEvents(): Promise<{ events: Event[] }> {
  return apiFetch('/api/v1/photographers/me/events');
}

export interface AssignedPhotographerRow {
  photographer_id: string;
  email: string;
  assigned_at: string;
}

export async function getEventPhotographers(
  eventId: string
): Promise<{ photographers: AssignedPhotographerRow[] }> {
  return apiFetch(`/api/v1/events/${eventId}/photographers`);
}

export async function downloadFavouritesZip(eventId: string): Promise<void> {
  const token = getGuestToken(eventId);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${baseUrl()}/api/v1/events/${eventId}/favourites/zip`, {
    method: 'POST',
    headers,
  });

  if (!response.ok) throw new Error(`HTTP ${response.status}`);

  const freshToken = response.headers.get('X-Guest-Token');
  if (freshToken) setGuestToken(eventId, freshToken);

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = response.headers.get('Content-Disposition')?.match(/filename="(.+?)"/)?.[1]
    ?? 'wedding-my-favourites.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

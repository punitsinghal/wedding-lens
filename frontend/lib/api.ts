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
  AdminEventDetail,
  PlatformHealth,
  EventAnalytics,
  AlbumTab,
  GalleryListResponse,
  Photo,
  PhotoListResponse,
  PhotoUploadResponse,
  ShareLinkResponse,
  FavouritesResponse,
  ShareTokenResponse,
  RemovalRequestCreateRequest,
  RemovalRequestCreateResponse,
  AdminRemovalRequestsResponse,
} from '@/types/api';

function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
}

// Parses a Content-Disposition header for the real filename. Handles both
// the quoted form (`filename="IMG_4521.JPG"`) and the RFC 5987 form used
// whenever the name has spaces/parens/unicode (`filename*=UTF-8''IMG%20...`),
// which Starlette emits instead of (never alongside) the quoted form.
function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const quoted = header.match(/filename="(.+?)"/)?.[1];
  if (quoted) return quoted;
  const encoded = header.match(/filename\*=(?:UTF-8|utf-8)''([^;]+)/)?.[1];
  if (encoded) {
    try {
      return decodeURIComponent(encoded);
    } catch {
      return encoded;
    }
  }
  return null;
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
    // Re-throw the parsed body (plus status, so callers can tell a genuine
    // 404 apart from a transient 5xx/network failure) for callers to inspect
    throw { ...(errorBody as object), status: response.status };
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

// Event-owner analytics (view/download/search totals) — owner-only endpoint.
export async function getEventAnalytics(eventId: string): Promise<EventAnalytics> {
  return apiFetch<EventAnalytics>(`/api/v1/events/${eventId}/analytics`);
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
  pageSize: number = 20,
  params: { status?: string; sort?: 'last_activity' | 'photo_count' } = {}
): Promise<AdminEventsResponse> {
  const qs = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (params.status) qs.set('status', params.status);
  if (params.sort) qs.set('sort', params.sort);
  return apiFetch<AdminEventsResponse>(`/api/v1/admin/events?${qs.toString()}`);
}

export async function adminGetEventDetail(eventId: string): Promise<AdminEventDetail> {
  return apiFetch<AdminEventDetail>(`/api/v1/admin/events/${eventId}`);
}

export async function adminGetPlatformHealth(): Promise<PlatformHealth> {
  return apiFetch<PlatformHealth>('/api/v1/admin/health');
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

// Unauthenticated image URL — safe to use directly as an <img src> or CSS
// background-image; the backend only ever serves the one photo the
// photographer chose as cover_photo_id, and only once the event is published.
export function getEventCoverUrl(slug: string): string {
  return `${baseUrl()}/api/v1/events/by-slug/${slug}/cover`;
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

// Guest photo-view beacon — fire-and-forget (204, may refresh guest token).
// Intentionally returns void rather than a Promise: callers (e.g. Lightbox)
// must not await this or handle its result — errors are swallowed here so a
// failed beacon never surfaces to the guest or blocks the UI.
export function recordPhotoView(eventId: string, photoId: string): void {
  guestApiFetch<void>(eventId, `/api/v1/events/${eventId}/photos/${photoId}/view`, {
    method: 'POST',
  }).catch(() => {
    // fire-and-forget — swallow errors, matches the backend's own
    // fire-and-forget contract for this beacon (design D5).
  });
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

export async function setPhotographerChoice(
  eventId: string,
  photoId: string,
  value: boolean
): Promise<Photo> {
  return apiFetch<Photo>(
    `/api/v1/events/${eventId}/photos/${photoId}/photographer-choice`,
    { method: 'PATCH', body: { is_photographer_choice: value } }
  );
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
// Guest uploads — guest-authenticated, presigned-R2 upload
//
// The guest-token/refresh/error-handling logic here is shared by both the
// `initiate` and `complete` calls below (either could plausibly 401 or
// 429) — the guest-token param (not guestApiFetch's internal
// getGuestToken(eventId)) and onTokenRefresh callback (not setGuestToken)
// are preserved exactly as this file's raw-fetch guest-upload calls have
// always used them.
// ---------------------------------------------------------------------------

async function guestUploadFetch<T>(
  eventId: string,
  path: string,
  guestToken: string,
  body: unknown,
  onTokenRefresh: (newToken: string) => void
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (guestToken) headers['Authorization'] = `Bearer ${guestToken}`;

  const response = await fetch(`${baseUrl()}${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  const refreshedToken = response.headers.get('X-Guest-Token');
  if (refreshedToken) {
    onTokenRefresh(refreshedToken);
  }

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
    // Status (and Retry-After, on a 429) let the caller distinguish a rate
    // limit from an ordinary rejection and show a wait time.
    const retryAfterHeader = response.headers.get('Retry-After');
    throw {
      ...(errorBody as object),
      status: response.status,
      retryAfter: retryAfterHeader ? parseInt(retryAfterHeader, 10) : undefined,
    };
  }

  return response.json() as Promise<T>;
}

export async function uploadGuestPhoto(
  eventId: string,
  guestToken: string,
  file: File,
  displayName: string | undefined,
  onTokenRefresh: (newToken: string) => void
): Promise<PhotoUploadResponse> {
  const { photo_id, upload_url } = await guestUploadFetch<{ photo_id: string; upload_url: string }>(
    eventId,
    `/api/v1/events/${eventId}/guest-uploads/initiate`,
    guestToken,
    { filename: file.name, file_size_bytes: file.size, display_name: displayName ?? null },
    onTokenRefresh
  );

  // PUT the file bytes straight to R2 — no guest token, no custom headers,
  // the presigned URL's query string is self-authenticating.
  const uploadResponse = await fetch(upload_url, { method: 'PUT', body: file });
  if (!uploadResponse.ok) {
    throw { status: uploadResponse.status };
  }

  return guestUploadFetch<PhotoUploadResponse>(
    eventId,
    `/api/v1/events/${eventId}/guest-uploads/${photo_id}/complete`,
    guestToken,
    { filename: file.name, display_name: displayName ?? null },
    onTokenRefresh
  );
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
  a.download = filenameFromContentDisposition(response.headers.get('Content-Disposition'))
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
    filenameFromContentDisposition(response.headers.get('Content-Disposition')) ?? 'photo.jpg';
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
  // Ask the backend for a presigned R2 URL for this chunk (owner-scoped,
  // same Bearer auth + `.detail` error handling as every other apiFetch call).
  const { url } = await apiFetch<{ chunk_index: number; url: string }>(
    `/api/v1/events/${eventId}/uploads/${sessionId}/chunks/${chunkIndex}/url`
  );

  // PUT the chunk bytes straight to R2 — the presigned URL's query string is
  // self-authenticating, so no Authorization header (or any other custom
  // header) is sent here, per docs/decisions/2026-08-22-presigned-url-image-delivery.md.
  const response = await fetch(url, { method: 'PUT', body: bytes.buffer as ArrayBuffer });

  if (!response.ok) {
    // R2 returns an XML error body on failure, not JSON — don't try to parse
    // it. Throwing an object with no `.detail` matches this file's existing
    // error shape and makes the caller's retry loop fall through to its
    // generic "Chunk upload failed" message, same as any other error without
    // a `.detail` field.
    throw { status: response.status };
  }
}

export async function completeUpload(
  eventId: string,
  sessionId: string,
  albumId?: string | null
): Promise<{ photo_id: string }> {
  return apiFetch(`/api/v1/events/${eventId}/uploads/${sessionId}/complete`, {
    method: 'POST',
    body: { album_id: albumId ?? null },
  });
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
// Removal requests — guest-authenticated
// ---------------------------------------------------------------------------

export async function submitRemovalRequest(
  eventId: string,
  data: RemovalRequestCreateRequest
): Promise<RemovalRequestCreateResponse> {
  const token = getGuestToken(eventId);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(`${baseUrl()}/api/v1/events/${eventId}/removal-requests`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    let errorBody: unknown;
    try { errorBody = await response.json(); } catch { errorBody = { detail: response.statusText }; }
    throw errorBody;
  }

  return response.json() as Promise<RemovalRequestCreateResponse>;
}

// ---------------------------------------------------------------------------
// Removal requests — admin
// ---------------------------------------------------------------------------

export async function adminGetRemovalRequests(
  status?: string
): Promise<AdminRemovalRequestsResponse> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : '';
  return apiFetch<AdminRemovalRequestsResponse>(`/api/v1/admin/removal-requests${qs}`);
}

export async function adminFulfillRemovalRequest(requestId: string): Promise<void> {
  return apiFetch<void>(`/api/v1/admin/removal-requests/${requestId}/fulfill`, {
    method: 'POST',
  });
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
  a.download = filenameFromContentDisposition(response.headers.get('Content-Disposition'))
    ?? 'wedding-my-favourites.zip';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

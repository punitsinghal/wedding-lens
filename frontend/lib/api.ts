// Typed fetch wrapper + auth header injection
// All API calls go through this module — never call fetch directly from components

import { getToken, getGuestToken, setGuestToken, clearGuestToken } from './auth';
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

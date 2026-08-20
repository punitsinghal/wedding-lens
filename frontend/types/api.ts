// TypeScript types matching the PicsLeLo backend API shapes

export type AccessMode = 'access-code' | 'magic-link-otp' | 'public';

export type EventStatus = 'draft' | 'published' | 'suspended' | 'deleted';

export type CeremonyCategory =
  | 'Ceremony'
  | 'Sangeet'
  | 'Mehendi'
  | 'Haldi'
  | 'Reception'
  | 'Family Photos';

export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
}

export interface Event {
  id: string;
  owner_id: string;
  name: string;
  bride_name: string;
  groom_name: string;
  event_date: string; // ISO date string
  slug: string;
  cover_photo_id: string | null;
  access_mode: AccessMode;
  access_code: string | null;
  otp_code: string | null;
  guest_access_enabled: boolean;
  guest_access_revoked_at: string | null;
  guest_uploads_enabled: boolean;
  status: EventStatus;
  deleted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface EventPublicOut {
  id: string;
  name: string;
  bride_name: string;
  groom_name: string;
  event_date: string | null;
  slug: string;
  cover_photo_id: string | null;
  access_mode: AccessMode;
  status: EventStatus;
  guest_uploads_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface GuestTokenOut {
  access_token: string;
  token_type: string;
}

export interface EventCreateRequest {
  name: string;
  bride_name: string;
  groom_name: string;
  event_date: string;
  access_mode: AccessMode;
  access_code?: string;
  slug?: string;
}

export interface EventUpdateRequest {
  name?: string;
  bride_name?: string;
  groom_name?: string;
  event_date?: string;
  access_mode?: AccessMode;
  access_code?: string;
  slug?: string;
  cover_photo_id?: string | null;
  guest_uploads_enabled?: boolean;
}

export type AlbumVisibility = 'public' | 'private';

export interface Album {
  id: string;
  event_id: string;
  name: string;
  ceremony_category: CeremonyCategory | null;
  cover_photo_id: string | null;
  sort_order: number;
  visibility: AlbumVisibility;
  created_at: string;
  updated_at: string;
}

export interface AlbumCreateRequest {
  name: string;
  ceremony_category?: CeremonyCategory;
  visibility?: AlbumVisibility;
}

export interface AlbumUpdateRequest {
  name?: string;
  ceremony_category?: CeremonyCategory | null;
  cover_photo_id?: string | null;
  visibility?: AlbumVisibility;
}

export interface AdminEvent extends Event {
  owner_email: string;
  photo_count: number;
  storage_used_bytes: number;
  last_activity_at: string; // ISO datetime
}

export interface AdminEventsResponse {
  items: AdminEvent[];
  total: number;
  page: number;
  page_size: number;
}

// Processing pipeline status breakdown — all 5 real processing_status values
// (pending/processing/complete are self-explanatory; failed = retryable,
// error = retries exhausted — see backend design D3).
export interface ProcessingMonitor {
  pending: number;
  processing: number;
  complete: number;
  failed: number;
  error: number;
}

export interface AdminEventDetail extends AdminEvent {
  processing_monitor: ProcessingMonitor;
}

export interface PlatformHealth {
  total_events: number;
  total_photos: number;
  total_storage_bytes: number;
  error_rate_24h: number; // 0-1 float
}

export interface EventAnalytics {
  total_views: number;
  total_downloads: number;
  total_searches: number;
}

export interface SlugTakenError {
  detail: 'slug_taken';
  suggestions: string[];
}

export interface ApiError {
  detail: string | SlugTakenError['detail'];
  suggestions?: string[];
}

export function isSlugTakenError(
  err: unknown
): err is { detail: 'slug_taken'; suggestions: string[] } {
  return (
    typeof err === 'object' &&
    err !== null &&
    'detail' in err &&
    (err as ApiError).detail === 'slug_taken'
  );
}

// ---------------------------------------------------------------------------
// Gallery types
// ---------------------------------------------------------------------------

export type UploadedBy = 'photographer' | 'guest';

export interface GalleryPhoto {
  id: string;
  thumbnail_url: string | null;
  is_photographer_choice: boolean;
  download_count: number;
  created_at: string;
  uploaded_by: UploadedBy;
  guest_display_name: string | null;
}

export interface GalleryListResponse {
  photos: GalleryPhoto[];
  total: number;
  limit: number;
  offset: number;
}

export interface AlbumTab {
  ceremony_category: string | null;
  label: string;
  photo_count: number;
}

// ---------------------------------------------------------------------------
// Photos — owner-only types
// ---------------------------------------------------------------------------

export interface Photo {
  id: string;
  event_id: string;
  album_id: string | null;
  filename: string;
  processing_status: string;
  thumbnail_url: string | null;
  is_photographer_choice: boolean;
  created_at: string;
}

export interface PhotoListResponse {
  items: Photo[];
  total: number;
  limit: number;
  offset: number;
}

export interface PhotoUploadResponse {
  id: string;
  event_id: string;
  album_id: string | null;
  filename: string;
  processing_status: string;
}

// Photo Actions
export interface FavouritePhoto {
  photo_id: string;
  thumbnail_url: string | null;
}

export interface FavouritesResponse {
  photos: FavouritePhoto[];
}

export interface ShareLinkResponse {
  share_url: string;
  expires_at: string;
}

export interface ShareTokenResponse {
  photo_id: string;
  event_id: string;
  event_slug: string | null;
}

// ---------------------------------------------------------------------------
// Photographer assignment types
// ---------------------------------------------------------------------------

export interface AssignedEvent {
  id: string;
  name: string;
  slug: string;
  status: string;
  bride_name: string | null;
  groom_name: string | null;
  created_at: string;
  event_date?: string | null;
}

// ---------------------------------------------------------------------------
// Privacy / removal request types
// ---------------------------------------------------------------------------

export type RemovalRequestStatus = 'pending' | 'fulfilled';

export interface RemovalRequest {
  id: string;
  event_id: string;
  submitted_at: string;
  guest_name: string;
  guest_email: string;
  description: string;
  status: RemovalRequestStatus;
  fulfilled_at: string | null;
}

export interface RemovalRequestCreateRequest {
  name: string;
  email: string;
  description: string;
}

export interface RemovalRequestCreateResponse {
  id: string;
  status: RemovalRequestStatus;
  message: string;
}

export interface AdminRemovalRequestsResponse {
  items: RemovalRequest[];
  pending_count: number;
}

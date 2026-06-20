// TypeScript types matching the WeddingLens backend API shapes

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
}

export interface Album {
  id: string;
  event_id: string;
  name: string;
  ceremony_category: CeremonyCategory | null;
  cover_photo_id: string | null;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface AlbumCreateRequest {
  name: string;
  ceremony_category?: CeremonyCategory;
}

export interface AlbumUpdateRequest {
  name?: string;
  ceremony_category?: CeremonyCategory | null;
  cover_photo_id?: string | null;
}

export interface AdminEvent extends Event {
  owner_email: string;
  photo_count: number;
}

export interface AdminEventsResponse {
  items: AdminEvent[];
  total: number;
  page: number;
  page_size: number;
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

export interface GalleryPhoto {
  id: string;
  thumbnail_url: string | null;
  is_photographer_choice: boolean;
  download_count: number;
  created_at: string;
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

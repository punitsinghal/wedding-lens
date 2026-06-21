'use client';

import { useState, useEffect, FormEvent } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import {
  getEvent,
  getPhotos,
  fetchAuthedBlob,
  updateEvent,
  deleteEvent,
  publishEvent,
  unpublishEvent,
  revokeGuestAccess,
  enableGuestAccess,
  getEventPhotographers,
  assignPhotographer,
  removePhotographer,
} from '@/lib/api';
import type { AssignedPhotographerRow } from '@/lib/api';
import { isAuthenticated, getCurrentUserId } from '@/lib/auth';
import { isSlugTakenError } from '@/types/api';
import type { Event, AccessMode, Photo } from '@/types/api';
import SlugField from '@/components/SlugField';
import StatusBadge from '@/components/StatusBadge';
import ConfirmDialog from '@/components/ConfirmDialog';

export default function EventDetailPage() {
  const router = useRouter();
  const params = useParams();
  const eventId = params.eventId as string;

  // Auth guard
  useEffect(() => {
    if (!isAuthenticated()) router.replace('/login');
  }, [router]);

  const [event, setEvent] = useState<Event | null>(null);
  const [isLoadingEvent, setIsLoadingEvent] = useState(true);
  const [loadError, setLoadError] = useState('');

  // Form state
  const [name, setName] = useState('');
  const [brideName, setBrideName] = useState('');
  const [groomName, setGroomName] = useState('');
  const [eventDate, setEventDate] = useState('');
  const [accessMode, setAccessMode] = useState<AccessMode>('public');
  const [accessCode, setAccessCode] = useState('');
  const [slug, setSlug] = useState('');
  const [slugSuggestions, setSlugSuggestions] = useState<string[]>([]);

  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Publish/Unpublish
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishError, setPublishError] = useState('');

  // Delete
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Guest access revocation
  const [isRevoking, setIsRevoking] = useState(false);
  const [revokeError, setRevokeError] = useState('');

  // Cover photo picker
  const [allPhotos, setAllPhotos] = useState<Photo[]>([]);
  const [coverBlobUrls, setCoverBlobUrls] = useState<Record<string, string>>({});
  const [photosLoading, setPhotosLoading] = useState(false);
  const [settingEventCover, setSettingEventCover] = useState(false);
  const [coverError, setCoverError] = useState('');

  // Photographer management
  const [photographers, setPhotographers] = useState<AssignedPhotographerRow[]>([]);
  const [assignEmail, setAssignEmail] = useState('');
  const [assignError, setAssignError] = useState('');
  const [isAssigning, setIsAssigning] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      getEvent(eventId),
      getPhotos(eventId, { limit: 100 }),
    ])
      .then(([ev, photoList]) => {
        setEvent(ev);
        setName(ev.name);
        setBrideName(ev.bride_name);
        setGroomName(ev.groom_name);
        setEventDate(ev.event_date);
        setAccessMode(ev.access_mode);
        setAccessCode(ev.access_code ?? '');
        setSlug(ev.slug);

        // Only the owner can list assigned photographers
        if (ev.owner_id === getCurrentUserId()) {
          getEventPhotographers(eventId).then((result) => {
            setPhotographers(result.photographers);
          });
        }

        // Only show photos that belong to an album
        const albumPhotos = photoList.items.filter((p) => p.album_id != null);
        setAllPhotos(albumPhotos);

        // Fetch thumbnails concurrently
        setPhotosLoading(true);
        const map: Record<string, string> = {};
        Promise.allSettled(
          albumPhotos
            .filter((p) => p.thumbnail_url)
            .map(async (p) => {
              const url = await fetchAuthedBlob(p.thumbnail_url!);
              map[p.id] = url;
            })
        ).then(() => {
          setCoverBlobUrls({ ...map });
          setPhotosLoading(false);
        });
      })
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setLoadError(apiErr?.detail ?? 'Failed to load event.');
      })
      .finally(() => setIsLoadingEvent(false));
  }, [eventId]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaveError('');
    setSaveSuccess(false);
    setSlugSuggestions([]);
    setIsPublishing(false);
    setPublishError('');

    if (accessMode === 'access-code' && !accessCode.trim()) {
      setSaveError('Access code is required for access-code mode.');
      return;
    }

    setIsSaving(true);
    try {
      const updated = await updateEvent(eventId, {
        name: name.trim(),
        bride_name: brideName.trim(),
        groom_name: groomName.trim(),
        event_date: eventDate,
        access_mode: accessMode,
        ...(accessMode === 'access-code' ? { access_code: accessCode.trim() } : {}),
        slug: slug.trim(),
      });
      setEvent(updated);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 3000);
    } catch (err: unknown) {
      if (isSlugTakenError(err)) {
        setSlugSuggestions(err.suggestions);
        setSaveError('That URL slug is already taken. Choose another or pick a suggestion.');
      } else {
        const apiErr = err as { detail?: string };
        setSaveError(apiErr?.detail ?? 'Failed to save changes.');
      }
    } finally {
      setIsSaving(false);
    }
  }

  async function handlePublishToggle() {
    if (!event) return;
    setPublishError('');
    setIsPublishing(true);
    try {
      let updated: Event;
      if (event.status === 'published') {
        updated = await unpublishEvent(eventId);
      } else {
        updated = await publishEvent(eventId);
      }
      setEvent(updated);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setPublishError(apiErr?.detail ?? 'Failed to change publish status.');
    } finally {
      setIsPublishing(false);
    }
  }

  async function handleDelete() {
    setIsDeleting(true);
    try {
      await deleteEvent(eventId);
      router.replace('/dashboard');
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setSaveError(apiErr?.detail ?? 'Failed to delete event.');
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  }

  async function handleGuestAccessToggle() {
    if (!event) return;
    setIsRevoking(true);
    setRevokeError('');
    try {
      if (event.guest_access_enabled) {
        await revokeGuestAccess(eventId);
        setEvent({ ...event, guest_access_enabled: false });
      } else {
        await enableGuestAccess(eventId);
        setEvent({ ...event, guest_access_enabled: true });
      }
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setRevokeError(apiErr?.detail ?? 'Failed to update guest access.');
    } finally {
      setIsRevoking(false);
    }
  }

  async function handleSetEventCover(photoId: string) {
    setCoverError('');
    setSettingEventCover(true);
    try {
      const updated = await updateEvent(eventId, { cover_photo_id: photoId });
      setEvent(updated);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setCoverError(apiErr?.detail ?? 'Failed to set cover photo.');
    } finally {
      setSettingEventCover(false);
    }
  }

  async function handleAssignPhotographer(e: FormEvent) {
    e.preventDefault();
    setAssignError('');
    setIsAssigning(true);
    try {
      const result = await assignPhotographer(eventId, assignEmail.trim());
      setPhotographers(prev => [...prev, { ...result, assigned_at: new Date().toISOString() }]);
      setAssignEmail('');
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      if (apiErr?.detail?.includes('already assigned')) {
        setAssignError('Already assigned to this event');
      } else if (apiErr?.detail?.includes('No user found')) {
        setAssignError('No account found for this email');
      } else {
        setAssignError(apiErr?.detail ?? 'Failed to assign photographer');
      }
    } finally {
      setIsAssigning(false);
    }
  }

  async function handleRemovePhotographer(photographerId: string) {
    setRemovingId(photographerId);
    try {
      await removePhotographer(eventId, photographerId);
      setPhotographers(prev => prev.filter(p => p.photographer_id !== photographerId));
    } catch (err: unknown) {
      // Could show a per-row error but keep it simple — just log
      console.error('Remove failed', err);
    } finally {
      setRemovingId(null);
    }
  }

  if (isLoadingEvent) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-gray-400 text-sm">
        Loading event...
      </div>
    );
  }

  if (loadError || !event) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="p-4 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {loadError || 'Event not found.'}
        </div>
        <Link href="/dashboard" className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const isOwner = event.owner_id === getCurrentUserId();

  return (
    <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <Link href="/dashboard" className="text-sm text-gray-500 hover:text-gray-700">
          &larr; Dashboard
        </Link>
        <span className="text-gray-300">/</span>
        <h1 className="text-xl font-bold text-gray-900 truncate">{event.name}</h1>
        <StatusBadge status={event.status} />
      </div>

      {/* Quick links */}
      <div className="flex gap-4 mb-6 text-sm flex-wrap">
        <Link
          href={`/events/${eventId}/photos`}
          className="text-blue-600 hover:underline"
        >
          Manage Photos
        </Link>
        <Link
          href={`/events/${eventId}/albums`}
          className="text-blue-600 hover:underline"
        >
          Manage Albums
        </Link>
        <Link
          href={`/events/${eventId}/qr`}
          className="text-blue-600 hover:underline"
        >
          QR Code
        </Link>
      </div>

      {/* Publish / Unpublish */}
      <div className="mb-6 p-4 bg-gray-50 border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium text-gray-700">
              {event.status === 'published' ? 'Event is published' : 'Event is not published'}
            </p>
            <p className="text-xs text-gray-400 mt-0.5">
              {event.status === 'published'
                ? 'Guests can access this event via its QR code or URL.'
                : 'Guests cannot access this event yet.'}
            </p>
            {publishError && (
              <p className="text-xs text-red-600 mt-1">{publishError}</p>
            )}
          </div>
          {isOwner && (
            <button
              onClick={handlePublishToggle}
              disabled={isPublishing || event.status === 'suspended' || event.status === 'deleted'}
              className={`flex-shrink-0 px-4 py-2 text-sm font-medium rounded-md focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed ${
                event.status === 'published'
                  ? 'bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 focus:ring-gray-400'
                  : 'bg-green-600 text-white hover:bg-green-700 focus:ring-green-500'
              }`}
            >
              {isPublishing
                ? 'Updating...'
                : event.status === 'published'
                ? 'Unpublish'
                : 'Publish'}
            </button>
          )}
        </div>

        {isOwner && event.status === 'published' && (
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-medium text-gray-700">
                  Guest Access: {event.guest_access_enabled ? 'Active' : 'Revoked'}
                </p>
                <p className="text-xs text-gray-400 mt-0.5">
                  {event.guest_access_enabled
                    ? 'Guests with valid sessions can access the gallery.'
                    : 'All guest sessions are invalidated. Re-enable to allow access again.'}
                </p>
              </div>
              <button
                onClick={handleGuestAccessToggle}
                disabled={isRevoking}
                className={`flex-shrink-0 px-4 py-2 text-sm font-medium rounded-md focus:outline-none focus:ring-2 disabled:opacity-50 disabled:cursor-not-allowed ${
                  event.guest_access_enabled
                    ? 'bg-red-50 border border-red-300 text-red-700 hover:bg-red-100 focus:ring-red-400'
                    : 'bg-green-600 text-white hover:bg-green-700 focus:ring-green-500'
                }`}
              >
                {isRevoking ? 'Updating...' : event.guest_access_enabled ? 'Revoke Access' : 'Enable Access'}
              </button>
            </div>
            {revokeError && <p className="mt-2 text-xs text-red-600">{revokeError}</p>}
          </div>
        )}
      </div>

      {/* Cover Photo */}
      {isOwner && (<div className="mb-6 p-4 bg-white border border-gray-200 rounded-lg">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-800">Event Cover Photo</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              Required to publish. Shown as the event thumbnail for guests.
            </p>
          </div>
          {event.cover_photo_id && (
            <span className="text-xs text-green-700 bg-green-50 border border-green-200 px-2 py-1 rounded-full">
              Cover set
            </span>
          )}
        </div>

        {coverError && (
          <p className="mb-3 text-xs text-red-600">{coverError}</p>
        )}

        {photosLoading && allPhotos.length === 0 ? (
          <p className="text-xs text-gray-400 py-4 text-center">Loading photos...</p>
        ) : allPhotos.length === 0 ? (
          <p className="text-xs text-gray-400 py-4 text-center">
            No photos in albums yet.{' '}
            <Link href={`/events/${eventId}/albums`} className="text-blue-600 hover:underline">
              Add photos to an album
            </Link>{' '}
            to set a cover.
          </p>
        ) : (
          <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
            {allPhotos.map((photo) => {
              const isCover = event.cover_photo_id === photo.id;
              const thumbSrc = coverBlobUrls[photo.id];
              return (
                <button
                  key={photo.id}
                  onClick={() => handleSetEventCover(photo.id)}
                  disabled={settingEventCover}
                  className={[
                    'relative aspect-square rounded-md overflow-hidden',
                    'transition-all duration-150 focus:outline-none',
                    isCover
                      ? 'ring-2 ring-blue-500 ring-offset-1'
                      : 'hover:ring-2 hover:ring-gray-400 hover:ring-offset-1',
                    settingEventCover ? 'opacity-50 cursor-wait' : 'cursor-pointer',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  title={isCover ? 'Current event cover' : `Set as event cover`}
                >
                  {thumbSrc ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={thumbSrc}
                      alt={photo.filename}
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  ) : (
                    <div className="absolute inset-0 flex items-center justify-center bg-gray-100 text-gray-400">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                    </div>
                  )}
                  {isCover && (
                    <span className="absolute top-1 right-1 flex items-center justify-center w-4 h-4 bg-blue-500 rounded-full shadow">
                      <svg className="w-2.5 h-2.5 text-white" viewBox="0 0 12 12" fill="none">
                        <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>)}

      {/* Edit form */}
      {!isOwner && (
        <div className="mb-4 p-3 bg-blue-50 border border-blue-200 rounded-md text-sm text-blue-700">
          You have view-only access to this event as an assigned photographer.
        </div>
      )}
      {saveError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {saveError}
        </div>
      )}
      {saveSuccess && (
        <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-md text-sm text-green-700">
          Changes saved successfully.
        </div>
      )}

      <form
        onSubmit={handleSave}
        className="space-y-5 bg-white border border-gray-200 rounded-lg p-6"
      >
        <h2 className="text-base font-semibold text-gray-800">Event Details</h2>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="name">
            Event Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            disabled={!isOwner}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-default"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="brideName">
              Bride&apos;s Name <span className="text-red-500">*</span>
            </label>
            <input
              id="brideName"
              type="text"
              value={brideName}
              onChange={(e) => setBrideName(e.target.value)}
              required
              disabled={!isOwner}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-default"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="groomName">
              Groom&apos;s Name <span className="text-red-500">*</span>
            </label>
            <input
              id="groomName"
              type="text"
              value={groomName}
              onChange={(e) => setGroomName(e.target.value)}
              required
              disabled={!isOwner}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-default"
            />
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="eventDate">
            Event Date <span className="text-red-500">*</span>
          </label>
          <input
            id="eventDate"
            type="date"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
            required
            disabled={!isOwner}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-default"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="accessMode">
            Guest Access Mode <span className="text-red-500">*</span>
          </label>
          <select
            id="accessMode"
            value={accessMode}
            onChange={(e) => setAccessMode(e.target.value as AccessMode)}
            disabled={!isOwner}
            className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-default"
          >
            <option value="public">Public — anyone with the link</option>
            <option value="access-code">Access Code — guests enter a code</option>
            <option value="magic-link-otp">Magic Link / OTP — guests verify by email</option>
          </select>
        </div>

        {accessMode === 'access-code' && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1" htmlFor="accessCode">
              Access Code <span className="text-red-500">*</span>
            </label>
            <input
              id="accessCode"
              type="text"
              value={accessCode}
              onChange={(e) => setAccessCode(e.target.value)}
              required
              disabled={!isOwner}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-default"
            />
          </div>
        )}

        {accessMode === 'magic-link-otp' && event.otp_code && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              OTP Code (share with guests)
            </label>
            <div className="flex items-center gap-2">
              <code className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm bg-gray-50 font-mono tracking-widest">
                {event.otp_code}
              </code>
              <button
                type="button"
                onClick={() => navigator.clipboard.writeText(event.otp_code!)}
                className="px-3 py-2 text-sm border border-gray-300 rounded-md hover:bg-gray-50"
              >
                Copy
              </button>
            </div>
            <p className="mt-1 text-xs text-gray-400">Share this code with guests via WhatsApp or email.</p>
          </div>
        )}

        <SlugField
          value={slug}
          onChange={(v) => {
            setSlug(v);
            setSlugSuggestions([]);
          }}
          suggestions={slugSuggestions}
          onSelectSuggestion={(s) => {
            setSlug(s);
            setSlugSuggestions([]);
          }}
          disabled={!isOwner}
        />

        {isOwner && (
          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={isSaving}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isSaving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </form>

      {/* Photographers — owner only */}
      {event.owner_id === getCurrentUserId() && (
        <div className="mt-6 p-4 bg-white border border-gray-200 rounded-lg">
          <h2 className="text-base font-semibold text-gray-800 mb-4">Photographers</h2>

          <form onSubmit={handleAssignPhotographer} className="flex gap-2 mb-4">
            <input
              type="email"
              value={assignEmail}
              onChange={(e) => { setAssignEmail(e.target.value); setAssignError(''); }}
              placeholder="photographer@studio.com"
              required
              className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={isAssigning}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isAssigning ? 'Assigning...' : 'Assign'}
            </button>
          </form>

          {assignError && (
            <p className="mb-3 text-xs text-red-600">{assignError}</p>
          )}

          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Currently assigned</p>
          {photographers.length === 0 ? (
            <p className="text-sm text-gray-400">No photographers assigned yet.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {photographers.map((p) => (
                <li key={p.photographer_id} className="flex items-center justify-between py-2 gap-4">
                  <div className="min-w-0">
                    <span className="text-sm text-gray-800 truncate">{p.email}</span>
                    <span className="ml-3 text-xs text-gray-400">
                      Assigned {new Date(p.assigned_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                    </span>
                  </div>
                  <button
                    onClick={() => handleRemovePhotographer(p.photographer_id)}
                    disabled={removingId === p.photographer_id}
                    className="text-xs text-red-600 hover:text-red-800 disabled:opacity-50 flex-shrink-0"
                  >
                    {removingId === p.photographer_id ? 'Removing...' : 'Remove'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Danger zone */}
      {isOwner && (
        <div className="mt-8 p-4 border border-red-200 bg-red-50 rounded-lg">
          <h3 className="text-sm font-semibold text-red-800 mb-1">Danger Zone</h3>
          <p className="text-xs text-red-700 mb-3">
            Deleting this event starts a 30-day grace period. During this time the event is
            inaccessible to guests but data is retained and can be recovered by an admin.
            After 30 days all photos, face embeddings, and records are permanently deleted.
          </p>
          <button
            onClick={() => setShowDeleteDialog(true)}
            disabled={isDeleting}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 disabled:opacity-60"
          >
            Delete Event
          </button>
        </div>
      )}

      <ConfirmDialog
        isOpen={showDeleteDialog}
        title="Delete Event"
        message={`This will delete "${event.name}". The event will be inaccessible to guests immediately. You have a 30-day window for admin recovery before all data is permanently purged.`}
        confirmText="DELETE"
        confirmLabel="Delete Event"
        onConfirm={handleDelete}
        onCancel={() => setShowDeleteDialog(false)}
        destructive
      />
    </div>
  );
}

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
  getEventAnalytics,
} from '@/lib/api';
import type { AssignedPhotographerRow } from '@/lib/api';
import { isAuthenticated, getCurrentUserId } from '@/lib/auth';
import { isSlugTakenError } from '@/types/api';
import type { Event, AccessMode, Photo, EventAnalytics } from '@/types/api';
import SlugField from '@/components/SlugField';
import StatusBadge from '@/components/StatusBadge';
import ConfirmDialog from '@/components/ConfirmDialog';

type TabKey = 'overview' | 'publish' | 'photographers' | 'danger';

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ChecklistItem({ checked, label }: { checked: boolean; label: string }) {
  return (
    <div className="flex items-center gap-3">
      <span
        className={`grid h-5 w-5 flex-none place-items-center rounded-full ${
          checked ? 'bg-accent-2-500' : 'bg-neutral-300'
        }`}
      >
        <CheckIcon className="h-3 w-3 text-bg" />
      </span>
      <span className="text-sm">{label}</span>
    </div>
  );
}

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
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

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
  const [consentChecked, setConsentChecked] = useState(false);

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

  // Event-owner analytics (S6) — owner-only endpoint
  const [analytics, setAnalytics] = useState<EventAnalytics | null>(null);
  const [analyticsError, setAnalyticsError] = useState('');

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

  // Fetch owner analytics once the event has loaded and ownership is known
  // (the endpoint is strictly owner-only — REQ-6c — so skip the call
  // entirely for assigned photographers to avoid a guaranteed 403).
  useEffect(() => {
    if (!event || event.owner_id !== getCurrentUserId()) return;
    setAnalyticsError('');
    getEventAnalytics(eventId)
      .then(setAnalytics)
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setAnalyticsError(apiErr?.detail ?? 'Failed to load analytics.');
      });
  }, [event, eventId]);

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
      // Reset consent checkbox after publish or unpublish so republish requires re-checking (AC-1d)
      setConsentChecked(false);
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
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-sm opacity-60">
        Loading event...
      </div>
    );
  }

  if (loadError || !event) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {loadError || 'Event not found.'}
        </div>
        <Link href="/dashboard" className="btn btn-secondary mt-4">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const isOwner = event.owner_id === getCurrentUserId();
  // REQ-31/AC-19 (event-management): the backend rejects publish when no cover
  // photo is set. Mirror that here so the button doesn't invite a doomed submit.
  const missingCoverPhoto = event.status !== 'published' && !event.cover_photo_id;
  const consentConfirmed = consentChecked || event.status === 'published';

  const TABS: { key: TabKey; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'publish', label: 'Publish & Access' },
  ];
  if (isOwner) {
    TABS.push({ key: 'photographers', label: 'Photographers' }, { key: 'danger', label: 'Danger Zone' });
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-8">
      {/* Header */}
      <p className="text-sm opacity-60 mb-1">
        <Link href="/dashboard" className="hover:text-accent">Dashboard</Link> / {event.name}
      </p>
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <h1 className="text-3xl sm:text-4xl truncate">{event.name}</h1>
        <StatusBadge status={event.status} />
      </div>

      {!isOwner && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-accent-2-100 text-accent-2-800 border border-accent-2-200">
          You have view-only access to this event as an assigned photographer.
        </div>
      )}

      {/* Tabs */}
      <div className="mb-6 flex items-center gap-2 border-b border-divider pb-4 flex-wrap" role="tablist" aria-label="Event settings sections">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`tag border-0 cursor-pointer ${
              activeTab === tab.key ? 'bg-accent text-bg' : 'tag-neutral'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {saveError && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {saveError}
        </div>
      )}
      {saveSuccess && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-accent-2-100 text-accent-2-800 border border-accent-2-200">
          Changes saved successfully.
        </div>
      )}

      {/* Overview tab: analytics + event identity */}
      {activeTab === 'overview' && (
        <>
          {isOwner && (
            <div className="card elev-sm mb-6">
              <h4>Analytics</h4>
              {analyticsError && (
                <p className="text-xs text-[#8c2018]">{analyticsError}</p>
              )}
              {analytics ? (
                <div className="grid grid-cols-3 gap-3 pt-1">
                  <div>
                    <p className="text-xs opacity-60">Views</p>
                    <p className="text-3xl">{analytics.total_views}</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-60">Downloads</p>
                    <p className="text-3xl">{analytics.total_downloads}</p>
                  </div>
                  <div>
                    <p className="text-xs opacity-60">Searches</p>
                    <p className="text-3xl">{analytics.total_searches}</p>
                  </div>
                </div>
              ) : !analyticsError ? (
                <p className="text-xs opacity-60">Loading analytics...</p>
              ) : null}
            </div>
          )}

          <form onSubmit={handleSave} className="card elev-sm space-y-5">
            <h4>Event Details</h4>

            <div className="field">
              <label htmlFor="name">
                Event Name <span className="text-accent">*</span>
              </label>
              <input
                id="name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                disabled={!isOwner}
                className="input"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="field">
                <label htmlFor="brideName">
                  Bride&apos;s Name <span className="text-accent">*</span>
                </label>
                <input
                  id="brideName"
                  type="text"
                  value={brideName}
                  onChange={(e) => setBrideName(e.target.value)}
                  required
                  disabled={!isOwner}
                  className="input"
                />
              </div>
              <div className="field">
                <label htmlFor="groomName">
                  Groom&apos;s Name <span className="text-accent">*</span>
                </label>
                <input
                  id="groomName"
                  type="text"
                  value={groomName}
                  onChange={(e) => setGroomName(e.target.value)}
                  required
                  disabled={!isOwner}
                  className="input"
                />
              </div>
            </div>

            <div className="field">
              <label htmlFor="eventDate">
                Event Date <span className="text-accent">*</span>
              </label>
              <input
                id="eventDate"
                type="date"
                value={eventDate}
                onChange={(e) => setEventDate(e.target.value)}
                required
                disabled={!isOwner}
                className="input"
              />
            </div>

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
                <button type="submit" disabled={isSaving} className="btn btn-primary">
                  {isSaving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            )}
          </form>
        </>
      )}

      {/* Publish & Access tab: cover photo, access mode, publish/consent, guest-access toggle */}
      {activeTab === 'publish' && (
        <div className="grid grid-cols-1 md:grid-cols-[minmax(0,1fr),360px] gap-6 items-start">
          {/* Left column */}
          <div className="space-y-6 min-w-0">
            {isOwner && (
              <div className="card elev-sm">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h4>Event Cover Photo</h4>
                    <p className="text-xs opacity-60 mt-0.5">
                      Required to publish. Shown as the event thumbnail for guests.
                    </p>
                  </div>
                  {event.cover_photo_id && (
                    <span className="tag tag-accent-2 flex-none">Cover set</span>
                  )}
                </div>

                {coverError && (
                  <p className="text-xs text-[#8c2018]">{coverError}</p>
                )}

                {photosLoading && allPhotos.length === 0 ? (
                  <p className="text-xs opacity-60 py-4 text-center">Loading photos...</p>
                ) : allPhotos.length === 0 ? (
                  <p className="text-xs opacity-60 py-4 text-center">
                    No photos in albums yet.{' '}
                    <Link href={`/events/${eventId}/albums`} className="text-accent hover:underline">
                      Add photos to an album
                    </Link>{' '}
                    to set a cover.
                  </p>
                ) : (
                  <div className="grid grid-cols-4 sm:grid-cols-6 gap-2 pt-1">
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
                              ? 'ring-2 ring-accent ring-offset-1'
                              : 'hover:ring-2 hover:ring-neutral-400 hover:ring-offset-1',
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
                            <div className="absolute inset-0 flex items-center justify-center bg-neutral-200 opacity-60">
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                              </svg>
                            </div>
                          )}
                          {isCover && (
                            <span className="absolute top-1 right-1 flex items-center justify-center w-4 h-4 bg-accent rounded-full shadow">
                              <CheckIcon className="w-2.5 h-2.5 text-bg" />
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            <form onSubmit={handleSave} className="card elev-sm space-y-5">
              <h4>Guest Access</h4>

              <div className="field">
                <label>
                  Guest Access Mode <span className="text-accent">*</span>
                </label>
                <div className="flex flex-col gap-3">
                  <label className="radio">
                    <input
                      type="radio"
                      name="accessMode"
                      value="public"
                      checked={accessMode === 'public'}
                      onChange={() => setAccessMode('public')}
                      disabled={!isOwner}
                    />
                    <span className="dot" />
                    <span>
                      Public
                      <span className="block text-xs opacity-60">Anyone with the link can view</span>
                    </span>
                  </label>
                  <label className="radio">
                    <input
                      type="radio"
                      name="accessMode"
                      value="access-code"
                      checked={accessMode === 'access-code'}
                      onChange={() => setAccessMode('access-code')}
                      disabled={!isOwner}
                    />
                    <span className="dot" />
                    <span>
                      Access Code
                      <span className="block text-xs opacity-60">Guests enter a code to view</span>
                    </span>
                  </label>
                  <label className="radio">
                    <input
                      type="radio"
                      name="accessMode"
                      value="magic-link-otp"
                      checked={accessMode === 'magic-link-otp'}
                      onChange={() => setAccessMode('magic-link-otp')}
                      disabled={!isOwner}
                    />
                    <span className="dot" />
                    <span>
                      Magic Link / OTP
                      <span className="block text-xs opacity-60">Guests verify by email</span>
                    </span>
                  </label>
                </div>
              </div>

              {accessMode === 'access-code' && (
                <div className="field">
                  <label htmlFor="accessCode">
                    Access Code <span className="text-accent">*</span>
                  </label>
                  <input
                    id="accessCode"
                    type="text"
                    value={accessCode}
                    onChange={(e) => setAccessCode(e.target.value)}
                    required
                    disabled={!isOwner}
                    className="input"
                  />
                </div>
              )}

              {accessMode === 'magic-link-otp' && event.otp_code && (
                <div className="field">
                  <label>OTP Code (share with guests)</label>
                  <div className="flex items-center gap-2">
                    <code className="input flex-1 font-mono tracking-widest">
                      {event.otp_code}
                    </code>
                    <button
                      type="button"
                      onClick={() => navigator.clipboard.writeText(event.otp_code!)}
                      className="btn btn-secondary flex-none"
                    >
                      Copy
                    </button>
                  </div>
                  <p className="mt-1 text-xs opacity-60">Share this code with guests via WhatsApp or email.</p>
                </div>
              )}

              {isOwner && (
                <div className="flex justify-end pt-2">
                  <button type="submit" disabled={isSaving} className="btn btn-primary">
                    {isSaving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              )}
            </form>

            {isOwner && event.status === 'published' && (
              <div className="card elev-sm">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h4>Guest Access: {event.guest_access_enabled ? 'Active' : 'Revoked'}</h4>
                    <p className="text-xs opacity-60 mt-0.5">
                      {event.guest_access_enabled
                        ? 'Guests with valid sessions can access the gallery.'
                        : 'All guest sessions are invalidated. Re-enable to allow access again.'}
                    </p>
                  </div>
                  <button
                    onClick={handleGuestAccessToggle}
                    disabled={isRevoking}
                    className={`btn flex-none ${event.guest_access_enabled ? 'btn-secondary' : 'btn-primary'}`}
                  >
                    {isRevoking ? 'Updating...' : event.guest_access_enabled ? 'Revoke Access' : 'Enable Access'}
                  </button>
                </div>
                {revokeError && <p className="mt-2 text-xs text-[#8c2018]">{revokeError}</p>}
              </div>
            )}
          </div>

          {/* Right column — publish readiness */}
          <div className="card elev-sm h-fit">
            <h4>Ready to publish</h4>
            <p className="text-sm opacity-70">
              {event.status === 'published'
                ? 'Guests can access this event via its QR code or URL.'
                : 'Guests cannot access this event yet.'}
            </p>
            {publishError && (
              <p className="text-xs text-[#8c2018]">{publishError}</p>
            )}

            <div className="space-y-2 pt-1">
              <ChecklistItem checked={!!event.cover_photo_id} label="Cover photo chosen" />
              <ChecklistItem checked={consentConfirmed} label="Consent confirmed" />
            </div>

            {isOwner && event.status !== 'published' && event.status !== 'suspended' && event.status !== 'deleted' && (
              <div className="pt-3 mt-1 border-t border-divider">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={consentChecked}
                    onChange={(e) => setConsentChecked(e.target.checked)}
                    className="mt-0.5 h-4 w-4 flex-shrink-0 rounded border-divider text-accent focus:ring-accent"
                  />
                  <span className="text-xs opacity-80 leading-relaxed">
                    I confirm that guests attending this event have been informed that their photos will be processed using face recognition to help them find themselves in the gallery.
                  </span>
                </label>
                {!consentChecked && (
                  <p className="mt-2 text-xs px-2 py-1.5 rounded bg-accent-100 text-accent-800 border border-accent-200">
                    Check the box above to enable the Publish button.
                  </p>
                )}
                {missingCoverPhoto && (
                  <p className="mt-2 text-xs px-2 py-1.5 rounded bg-accent-100 text-accent-800 border border-accent-200">
                    Set a cover photo (above) to enable the Publish button.
                  </p>
                )}
              </div>
            )}

            {isOwner && (
              <div className="pt-3">
                <button
                  onClick={handlePublishToggle}
                  disabled={
                    isPublishing ||
                    event.status === 'suspended' ||
                    event.status === 'deleted' ||
                    (event.status !== 'published' && !consentChecked) ||
                    missingCoverPhoto
                  }
                  title={
                    event.status !== 'published' && !consentChecked
                      ? 'You must check the consent confirmation below before publishing.'
                      : missingCoverPhoto
                      ? 'Set a cover photo above before publishing.'
                      : undefined
                  }
                  className={`btn btn-block ${event.status === 'published' ? 'btn-secondary' : 'btn-primary'}`}
                >
                  {isPublishing
                    ? 'Updating...'
                    : event.status === 'published'
                    ? 'Unpublish'
                    : 'Publish'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Photographers tab — owner only */}
      {activeTab === 'photographers' && isOwner && (
        <div className="card elev-sm">
          <h4>Photographers</h4>

          <form onSubmit={handleAssignPhotographer} className="flex gap-2 items-start pt-1">
            <div className="field flex-1 !gap-0">
              <input
                type="email"
                value={assignEmail}
                onChange={(e) => { setAssignEmail(e.target.value); setAssignError(''); }}
                placeholder="photographer@studio.com"
                required
                className="input"
              />
            </div>
            <button type="submit" disabled={isAssigning} className="btn btn-primary flex-none">
              {isAssigning ? 'Assigning...' : 'Assign'}
            </button>
          </form>

          {assignError && (
            <p className="text-xs text-[#8c2018]">{assignError}</p>
          )}

          <p className="text-xs opacity-60 uppercase tracking-wide pt-2">Currently assigned</p>
          {photographers.length === 0 ? (
            <p className="text-sm opacity-60">No photographers assigned yet.</p>
          ) : (
            <ul className="divide-y divide-divider">
              {photographers.map((p) => (
                <li key={p.photographer_id} className="flex items-center justify-between py-2 gap-4">
                  <div className="min-w-0">
                    <span className="text-sm truncate">{p.email}</span>
                    <span className="ml-3 text-xs opacity-60">
                      Assigned {new Date(p.assigned_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                    </span>
                  </div>
                  <button
                    onClick={() => handleRemovePhotographer(p.photographer_id)}
                    disabled={removingId === p.photographer_id}
                    className="btn btn-danger text-xs px-3 py-1 flex-none"
                  >
                    {removingId === p.photographer_id ? 'Removing...' : 'Remove'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Danger Zone tab — owner only */}
      {activeTab === 'danger' && isOwner && (
        <div className="card elev-sm">
          <h4>Danger Zone</h4>
          <div className="px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
            Deleting this event starts a 30-day grace period. During this time the event is
            inaccessible to guests but data is retained and can be recovered by an admin.
            After 30 days all photos, face embeddings, and records are permanently deleted.
          </div>
          <div>
            <button
              onClick={() => setShowDeleteDialog(true)}
              disabled={isDeleting}
              className="btn btn-danger-solid"
            >
              Delete Event
            </button>
          </div>
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

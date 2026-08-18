'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  adminGetEvents,
  adminSuspendEvent,
  adminUnsuspendEvent,
  adminDeleteEvent,
  adminGetRemovalRequests,
  adminFulfillRemovalRequest,
  adminGetPlatformHealth,
} from '@/lib/api';
import type { AdminEvent, RemovalRequest, PlatformHealth } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';
import ConfirmDialog from '@/components/ConfirmDialog';
import { formatBytes, formatDateTime, formatPercent } from '@/lib/format';

const PAGE_SIZE = 20;

export default function AdminPage() {
  const [events, setEvents] = useState<AdminEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  // Per-row action state
  const [actionError, setActionError] = useState('');
  const [actingOnId, setActingOnId] = useState<string | null>(null);

  // Delete confirm
  const [deletingEvent, setDeletingEvent] = useState<AdminEvent | null>(null);

  // D6: Removal requests
  const [removalRequests, setRemovalRequests] = useState<RemovalRequest[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [removalLoading, setRemovalLoading] = useState(true);
  const [removalError, setRemovalError] = useState('');
  const [fulfillingId, setFulfillingId] = useState<string | null>(null);

  // Platform health dashboard
  const [health, setHealth] = useState<PlatformHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState('');

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const loadEvents = useCallback(() => {
    setIsLoading(true);
    setError('');
    adminGetEvents(page, PAGE_SIZE)
      .then(({ items, total: t }) => {
        setEvents(items);
        setTotal(t);
      })
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to load events.');
      })
      .finally(() => setIsLoading(false));
  }, [page]);

  useEffect(() => {
    loadEvents();
  }, [loadEvents]);

  // Platform health — loaded once on mount (no caching, D6)
  useEffect(() => {
    setHealthLoading(true);
    setHealthError('');
    adminGetPlatformHealth()
      .then(setHealth)
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setHealthError(apiErr?.detail ?? 'Failed to load platform health.');
      })
      .finally(() => setHealthLoading(false));
  }, []);

  async function handleSuspend(event: AdminEvent) {
    setActionError('');
    setActingOnId(event.id);
    try {
      const updated = await adminSuspendEvent(event.id);
      setEvents((prev) =>
        prev.map((e) => (e.id === event.id ? { ...e, status: updated.status } : e))
      );
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setActionError(apiErr?.detail ?? 'Failed to suspend event.');
    } finally {
      setActingOnId(null);
    }
  }

  async function handleUnsuspend(event: AdminEvent) {
    setActionError('');
    setActingOnId(event.id);
    try {
      const updated = await adminUnsuspendEvent(event.id);
      setEvents((prev) =>
        prev.map((e) => (e.id === event.id ? { ...e, status: updated.status } : e))
      );
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setActionError(apiErr?.detail ?? 'Failed to unsuspend event.');
    } finally {
      setActingOnId(null);
    }
  }

  async function handleAdminDelete(event: AdminEvent) {
    setActionError('');
    setActingOnId(event.id);
    try {
      await adminDeleteEvent(event.id);
      setEvents((prev) => prev.filter((e) => e.id !== event.id));
      setTotal((t) => t - 1);
      setDeletingEvent(null);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setActionError(apiErr?.detail ?? 'Failed to delete event.');
      setDeletingEvent(null);
    } finally {
      setActingOnId(null);
    }
  }

  // D6: load pending removal requests on mount
  useEffect(() => {
    setRemovalLoading(true);
    setRemovalError('');
    adminGetRemovalRequests('pending')
      .then(({ items, pending_count }) => {
        setRemovalRequests(items);
        setPendingCount(pending_count);
      })
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setRemovalError(apiErr?.detail ?? 'Failed to load removal requests.');
      })
      .finally(() => setRemovalLoading(false));
  }, []);

  async function handleFulfill(requestId: string) {
    setFulfillingId(requestId);
    try {
      await adminFulfillRemovalRequest(requestId);
      setRemovalRequests((prev) => prev.filter((r) => r.id !== requestId));
      setPendingCount((c) => Math.max(0, c - 1));
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setRemovalError(apiErr?.detail ?? 'Failed to mark request as fulfilled.');
    } finally {
      setFulfillingId(null);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
      <div className="flex items-center gap-3 mb-1 flex-wrap">
        <h1 className="text-4xl">All events</h1>
        {/* D6: pending removal requests badge */}
        {pendingCount > 0 && (
          <span className="tag tag-accent">
            {pendingCount} removal {pendingCount === 1 ? 'request' : 'requests'}
          </span>
        )}
      </div>
      <p className="text-sm opacity-60 mb-8">
        {total > 0 ? `${total} total events` : 'No events found'}
      </p>

      {/* Platform health dashboard (REQ-7, design D6) */}
      <div className="mb-8">
        <h2 className="text-2xl mb-3">Platform health</h2>
        {healthError && (
          <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
            {healthError}
          </div>
        )}
        {healthLoading ? (
          <div className="text-sm opacity-60">Loading platform health...</div>
        ) : health ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Active events</p>
              <p className="font-heading text-4xl">{health.total_events}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Photos stored</p>
              <p className="font-heading text-4xl">{health.total_photos}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Storage used</p>
              <p className="font-heading text-4xl">{formatBytes(health.total_storage_bytes)}</p>
            </div>
            <div className={`card ${health.error_rate_24h > 0.1 ? 'bg-accent-100' : ''}`}>
              <p className="text-[11px] uppercase tracking-wide opacity-60">Errors (24h)</p>
              <p
                className={`font-heading text-4xl ${
                  health.error_rate_24h > 0.1 ? 'text-accent-800' : ''
                }`}
              >
                {formatPercent(health.error_rate_24h)}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error}
        </div>
      )}
      {actionError && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {actionError}
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-sm opacity-60">Loading events...</div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="table-organic">
              <thead>
                <tr>
                  <th>Event</th>
                  <th>Owner</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th className="text-right">Photos</th>
                  <th className="text-right">Storage</th>
                  <th>Last activity</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="text-center py-12 opacity-60">
                      No events on this page.
                    </td>
                  </tr>
                ) : (
                  events.map((event) => (
                    <tr key={event.id}>
                      <td>
                        <Link
                          href={`/admin/events/${event.id}`}
                          className="font-medium hover:text-accent truncate max-w-xs block"
                        >
                          {event.name}
                        </Link>
                        <div className="text-xs opacity-50 font-mono">/{event.slug}</div>
                      </td>
                      <td className="opacity-70 truncate max-w-[180px]">
                        {event.owner_email}
                      </td>
                      <td className="opacity-70 whitespace-nowrap">
                        {new Date(event.event_date).toLocaleDateString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </td>
                      <td>
                        <StatusBadge status={event.status} />
                      </td>
                      <td className="text-right opacity-70">{event.photo_count}</td>
                      <td className="text-right opacity-70 whitespace-nowrap">
                        {formatBytes(event.storage_used_bytes)}
                      </td>
                      <td className="opacity-70 whitespace-nowrap">
                        {formatDateTime(event.last_activity_at)}
                      </td>
                      <td>
                        <div className="flex justify-end gap-2">
                          {event.status === 'suspended' ? (
                            <button
                              onClick={() => handleUnsuspend(event)}
                              disabled={actingOnId === event.id}
                              className="btn btn-secondary text-xs px-3 py-1"
                            >
                              Unsuspend
                            </button>
                          ) : event.status !== 'deleted' ? (
                            <button
                              onClick={() => handleSuspend(event)}
                              disabled={actingOnId === event.id}
                              className="btn btn-secondary text-xs px-3 py-1"
                            >
                              Suspend
                            </button>
                          ) : null}
                          <button
                            onClick={() => setDeletingEvent(event)}
                            disabled={actingOnId === event.id}
                            className="btn btn-danger text-xs px-3 py-1"
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile card list */}
          <div className="sm:hidden space-y-3">
            {events.length === 0 ? (
              <p className="text-center py-12 text-sm opacity-60">No events on this page.</p>
            ) : (
              events.map((event) => (
                <div key={event.id} className="card elev-sm">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <Link
                        href={`/admin/events/${event.id}`}
                        className="card-title hover:text-accent truncate block"
                      >
                        {event.name}
                      </Link>
                      <p className="text-xs opacity-50 font-mono">/{event.slug}</p>
                    </div>
                    <StatusBadge status={event.status} />
                  </div>
                  <p className="text-xs opacity-70">{event.owner_email}</p>
                  <p className="text-xs opacity-60">
                    {new Date(event.event_date).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}{' '}
                    &middot; {event.photo_count} photos &middot; {formatBytes(event.storage_used_bytes)}
                  </p>
                  <p className="text-xs opacity-60">
                    Last activity: {formatDateTime(event.last_activity_at)}
                  </p>
                  <div className="flex gap-2 mt-1">
                    {event.status === 'suspended' ? (
                      <button
                        onClick={() => handleUnsuspend(event)}
                        disabled={actingOnId === event.id}
                        className="btn btn-secondary text-xs px-3 py-1"
                      >
                        Unsuspend
                      </button>
                    ) : event.status !== 'deleted' ? (
                      <button
                        onClick={() => handleSuspend(event)}
                        disabled={actingOnId === event.id}
                        className="btn btn-secondary text-xs px-3 py-1"
                      >
                        Suspend
                      </button>
                    ) : null}
                    <button
                      onClick={() => setDeletingEvent(event)}
                      disabled={actingOnId === event.id}
                      className="btn btn-danger text-xs px-3 py-1"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between mt-6">
              <p className="text-sm opacity-60">
                Page {page} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="btn btn-secondary"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="btn btn-secondary"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* D6: Pending face data removal requests */}
      <div className="mt-10">
        <div className="flex items-center gap-3 mb-4">
          <h2 className="text-2xl">Face data removal requests</h2>
          {pendingCount > 0 && <span className="tag tag-accent">{pendingCount} pending</span>}
        </div>

        {removalError && (
          <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
            {removalError}
          </div>
        )}

        {removalLoading ? (
          <div className="text-center py-8 text-sm opacity-60">Loading removal requests...</div>
        ) : removalRequests.length === 0 ? (
          <div className="card text-center py-8 text-sm opacity-60">
            No pending removal requests.
          </div>
        ) : (
          <div className="space-y-3">
            {removalRequests.map((req) => (
              <div
                key={req.id}
                className="card elev-sm sm:flex-row sm:items-center sm:justify-between gap-4"
              >
                <div className="min-w-0 flex-1">
                  <p className="card-title truncate">{req.guest_name}</p>
                  <p className="text-xs opacity-60">{req.guest_email}</p>
                  <p className="text-xs opacity-50 font-mono mt-1">
                    {new Date(req.submitted_at).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}{' '}
                    &middot; event {req.event_id}
                  </p>
                  <p className="text-sm mt-2">{req.description}</p>
                </div>
                <button
                  onClick={() => handleFulfill(req.id)}
                  disabled={fulfillingId === req.id}
                  className="btn btn-primary flex-shrink-0"
                >
                  {fulfillingId === req.id ? 'Marking...' : 'Mark fulfilled'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Admin delete confirmation — hard delete, no grace period */}
      <ConfirmDialog
        isOpen={deletingEvent !== null}
        title="Admin Delete Event"
        message={`Permanently delete "${deletingEvent?.name}"? This is a hard delete — no grace period. All photos, face embeddings, and records will be immediately purged. This cannot be undone.`}
        confirmText="DELETE"
        confirmLabel="Permanently Delete"
        onConfirm={() => deletingEvent && handleAdminDelete(deletingEvent)}
        onCancel={() => setDeletingEvent(null)}
        destructive
      />
    </div>
  );
}

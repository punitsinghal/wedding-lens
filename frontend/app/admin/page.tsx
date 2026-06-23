'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  adminGetEvents,
  adminSuspendEvent,
  adminUnsuspendEvent,
  adminDeleteEvent,
  adminGetRemovalRequests,
  adminFulfillRemovalRequest,
} from '@/lib/api';
import type { AdminEvent, RemovalRequest } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';
import ConfirmDialog from '@/components/ConfirmDialog';

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
      <div className="flex items-center gap-3 mb-2">
        <h1 className="text-2xl font-bold text-gray-900">Admin — All Events</h1>
        {/* D6: pending removal requests badge */}
        {pendingCount > 0 && (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
            {pendingCount} removal {pendingCount === 1 ? 'request' : 'requests'}
          </span>
        )}
      </div>
      <p className="text-sm text-gray-500 mb-6">
        {total > 0 ? `${total} total events` : 'No events found'}
      </p>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}
      {actionError && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {actionError}
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading events...</div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden sm:block overflow-x-auto">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Event</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Owner</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Date</th>
                  <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Photos</th>
                  <th className="text-right px-4 py-3 font-medium text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="text-center py-12 text-gray-400">
                      No events on this page.
                    </td>
                  </tr>
                ) : (
                  events.map((event) => (
                    <tr
                      key={event.id}
                      className="border-b border-gray-100 hover:bg-gray-50"
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900 truncate max-w-xs">
                          {event.name}
                        </div>
                        <div className="text-xs text-gray-400 font-mono">/{event.slug}</div>
                      </td>
                      <td className="px-4 py-3 text-gray-600 truncate max-w-[180px]">
                        {event.owner_email}
                      </td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                        {new Date(event.event_date).toLocaleDateString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={event.status} />
                      </td>
                      <td className="px-4 py-3 text-right text-gray-600">
                        {event.photo_count}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex justify-end gap-2">
                          {event.status === 'suspended' ? (
                            <button
                              onClick={() => handleUnsuspend(event)}
                              disabled={actingOnId === event.id}
                              className="text-xs text-green-700 hover:text-green-900 font-medium disabled:opacity-50"
                            >
                              Unsuspend
                            </button>
                          ) : event.status !== 'deleted' ? (
                            <button
                              onClick={() => handleSuspend(event)}
                              disabled={actingOnId === event.id}
                              className="text-xs text-yellow-700 hover:text-yellow-900 font-medium disabled:opacity-50"
                            >
                              Suspend
                            </button>
                          ) : null}
                          <button
                            onClick={() => setDeletingEvent(event)}
                            disabled={actingOnId === event.id}
                            className="text-xs text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
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
              <p className="text-center py-12 text-gray-400 text-sm">No events on this page.</p>
            ) : (
              events.map((event) => (
                <div
                  key={event.id}
                  className="bg-white border border-gray-200 rounded-lg p-4"
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <p className="font-medium text-gray-900">{event.name}</p>
                      <p className="text-xs text-gray-400 font-mono">/{event.slug}</p>
                    </div>
                    <StatusBadge status={event.status} />
                  </div>
                  <p className="text-xs text-gray-500">{event.owner_email}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {new Date(event.event_date).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}{' '}
                    &middot; {event.photo_count} photos
                  </p>
                  <div className="flex gap-3 mt-3">
                    {event.status === 'suspended' ? (
                      <button
                        onClick={() => handleUnsuspend(event)}
                        disabled={actingOnId === event.id}
                        className="text-xs text-green-700 hover:text-green-900 font-medium disabled:opacity-50"
                      >
                        Unsuspend
                      </button>
                    ) : event.status !== 'deleted' ? (
                      <button
                        onClick={() => handleSuspend(event)}
                        disabled={actingOnId === event.id}
                        className="text-xs text-yellow-700 hover:text-yellow-900 font-medium disabled:opacity-50"
                      >
                        Suspend
                      </button>
                    ) : null}
                    <button
                      onClick={() => setDeletingEvent(event)}
                      disabled={actingOnId === event.id}
                      className="text-xs text-red-600 hover:text-red-800 font-medium disabled:opacity-50"
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
              <p className="text-sm text-gray-500">
                Page {page} of {totalPages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page === totalPages}
                  className="px-3 py-1.5 text-sm border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed"
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
          <h2 className="text-lg font-semibold text-gray-900">Face Data Removal Requests</h2>
          {pendingCount > 0 && (
            <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
              {pendingCount} pending
            </span>
          )}
        </div>

        {removalError && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
            {removalError}
          </div>
        )}

        {removalLoading ? (
          <div className="text-center py-8 text-gray-400 text-sm">Loading removal requests...</div>
        ) : removalRequests.length === 0 ? (
          <div className="text-center py-8 text-gray-400 text-sm bg-gray-50 rounded-lg border border-gray-200">
            No pending removal requests.
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden sm:block overflow-x-auto">
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Guest</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Event ID</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Submitted</th>
                    <th className="text-left px-4 py-3 font-medium text-gray-600">Description</th>
                    <th className="text-right px-4 py-3 font-medium text-gray-600">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {removalRequests.map((req) => (
                    <tr key={req.id} className="border-b border-gray-100 hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">{req.guest_name}</div>
                        <div className="text-xs text-gray-400">{req.guest_email}</div>
                      </td>
                      <td className="px-4 py-3 text-gray-600 font-mono text-xs">
                        {req.event_id}
                      </td>
                      <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                        {new Date(req.submitted_at).toLocaleDateString('en-IN', {
                          day: 'numeric',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </td>
                      <td className="px-4 py-3 text-gray-600 max-w-xs">
                        <p className="truncate">{req.description}</p>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => handleFulfill(req.id)}
                          disabled={fulfillingId === req.id}
                          className="text-xs text-green-700 hover:text-green-900 font-medium disabled:opacity-50"
                        >
                          {fulfillingId === req.id ? 'Marking...' : 'Mark fulfilled'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile card list */}
            <div className="sm:hidden space-y-3">
              {removalRequests.map((req) => (
                <div key={req.id} className="bg-white border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <p className="font-medium text-gray-900">{req.guest_name}</p>
                      <p className="text-xs text-gray-400">{req.guest_email}</p>
                    </div>
                    <button
                      onClick={() => handleFulfill(req.id)}
                      disabled={fulfillingId === req.id}
                      className="text-xs text-green-700 hover:text-green-900 font-medium disabled:opacity-50 flex-shrink-0"
                    >
                      {fulfillingId === req.id ? 'Marking...' : 'Mark fulfilled'}
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 font-mono mb-1">{req.event_id}</p>
                  <p className="text-xs text-gray-400 mb-2">
                    {new Date(req.submitted_at).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </p>
                  <p className="text-xs text-gray-600 line-clamp-2">{req.description}</p>
                </div>
              ))}
            </div>
          </>
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

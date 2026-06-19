'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  adminGetEvents,
  adminSuspendEvent,
  adminUnsuspendEvent,
  adminDeleteEvent,
} from '@/lib/api';
import type { AdminEvent } from '@/types/api';
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

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Admin — All Events</h1>
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

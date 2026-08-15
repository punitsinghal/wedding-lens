'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { adminGetEventDetail } from '@/lib/api';
import type { AdminEventDetail } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';
import { formatBytes, formatDateTime } from '@/lib/format';

export default function AdminEventDetailPage() {
  const params = useParams();
  const eventId = params.eventId as string;

  const [detail, setDetail] = useState<AdminEventDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const loadDetail = useCallback(() => {
    setIsLoading(true);
    setError('');
    adminGetEventDetail(eventId)
      .then(setDetail)
      .catch((err: unknown) => {
        const apiErr = err as { detail?: string };
        setError(apiErr?.detail ?? 'Failed to load event detail.');
      })
      .finally(() => setIsLoading(false));
  }, [eventId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8">
      <div className="flex items-center gap-3 mb-6">
        <Link href="/admin" className="text-sm text-gray-500 hover:text-gray-700">
          &larr; Admin — All Events
        </Link>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-gray-400 text-sm">Loading event...</div>
      ) : !detail ? null : (
        <>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-2xl font-bold text-gray-900 truncate">{detail.name}</h1>
            <StatusBadge status={detail.status} />
          </div>
          <p className="text-xs text-gray-400 font-mono mb-6">/{detail.slug}</p>

          {/* Context fields (D1) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Owner</p>
              <p className="text-sm font-medium text-gray-900 truncate">{detail.owner_email}</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Photos</p>
              <p className="text-xl font-semibold text-gray-900">{detail.photo_count}</p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Storage Used</p>
              <p className="text-xl font-semibold text-gray-900">
                {formatBytes(detail.storage_used_bytes)}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Last Activity</p>
              <p className="text-sm font-medium text-gray-900">
                {formatDateTime(detail.last_activity_at)}
              </p>
            </div>
          </div>

          {/* Processing monitor (D3) */}
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Processing Monitor</h2>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-8">
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Pending</p>
              <p className="text-xl font-semibold text-gray-900">
                {detail.processing_monitor.pending}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Processing</p>
              <p className="text-xl font-semibold text-gray-900">
                {detail.processing_monitor.processing}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Complete</p>
              <p className="text-xl font-semibold text-green-700">
                {detail.processing_monitor.complete}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Failed (retrying)</p>
              <p className="text-xl font-semibold text-yellow-700">
                {detail.processing_monitor.failed}
              </p>
            </div>
            <div className="bg-white border border-gray-200 rounded-lg p-4">
              <p className="text-xs text-gray-500">Error (exhausted)</p>
              <p className="text-xl font-semibold text-red-700">
                {detail.processing_monitor.error}
              </p>
            </div>
          </div>

          <table className="w-full text-sm border-collapse">
            <tbody>
              <tr className="border-b border-gray-100">
                <td className="py-2 pr-4 text-gray-500">Bride / Groom</td>
                <td className="py-2 text-gray-900">
                  {detail.bride_name} &amp; {detail.groom_name}
                </td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="py-2 pr-4 text-gray-500">Event Date</td>
                <td className="py-2 text-gray-900">
                  {detail.event_date
                    ? new Date(detail.event_date).toLocaleDateString('en-IN', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })
                    : '—'}
                </td>
              </tr>
              <tr className="border-b border-gray-100">
                <td className="py-2 pr-4 text-gray-500">Access Mode</td>
                <td className="py-2 text-gray-900">{detail.access_mode}</td>
              </tr>
              <tr>
                <td className="py-2 pr-4 text-gray-500">Created</td>
                <td className="py-2 text-gray-900">{formatDateTime(detail.created_at)}</td>
              </tr>
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

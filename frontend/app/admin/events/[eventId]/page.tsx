'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { adminGetEventDetail } from '@/lib/api';
import type { AdminEventDetail } from '@/types/api';
import StatusBadge from '@/components/StatusBadge';
import Breadcrumb from '@/components/Breadcrumb';
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
      <Breadcrumb
        items={[
          { label: 'All events', href: '/admin' },
          { label: detail?.name ?? '...' },
        ]}
      />

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="text-center py-16 text-sm opacity-60">Loading event...</div>
      ) : !detail ? null : (
        <>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="text-3xl sm:text-4xl truncate">{detail.name}</h1>
            <StatusBadge status={detail.status} />
          </div>
          <p className="text-xs opacity-50 font-mono mb-6">/{detail.slug}</p>

          {/* Context fields (D1) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Owner</p>
              <p className="text-sm font-medium truncate">{detail.owner_email}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Photos</p>
              <p className="font-heading text-3xl">{detail.photo_count}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Storage used</p>
              <p className="font-heading text-3xl">{formatBytes(detail.storage_used_bytes)}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Last activity</p>
              <p className="text-sm font-medium">{formatDateTime(detail.last_activity_at)}</p>
            </div>
          </div>

          {/* Processing monitor (D3) */}
          <h2 className="text-2xl mb-3">Processing monitor</h2>
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-8">
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Pending</p>
              <p className="font-heading text-3xl">{detail.processing_monitor.pending}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Processing</p>
              <p className="font-heading text-3xl">{detail.processing_monitor.processing}</p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Complete</p>
              <p className="font-heading text-3xl text-accent-2-700">
                {detail.processing_monitor.complete}
              </p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Failed (retrying)</p>
              <p className="font-heading text-3xl text-accent-700">
                {detail.processing_monitor.failed}
              </p>
            </div>
            <div className="card">
              <p className="text-[11px] uppercase tracking-wide opacity-60">Error (exhausted)</p>
              <p className="font-heading text-3xl" style={{ color: '#8c2018' }}>
                {detail.processing_monitor.error}
              </p>
            </div>
          </div>

          <table className="w-full text-sm border-collapse">
            <tbody>
              <tr className="border-b border-divider">
                <td className="py-2 pr-4 opacity-60">Bride / Groom</td>
                <td className="py-2">
                  {detail.bride_name} &amp; {detail.groom_name}
                </td>
              </tr>
              <tr className="border-b border-divider">
                <td className="py-2 pr-4 opacity-60">Event Date</td>
                <td className="py-2">
                  {detail.event_date
                    ? new Date(detail.event_date).toLocaleDateString('en-IN', {
                        day: 'numeric',
                        month: 'short',
                        year: 'numeric',
                      })
                    : '—'}
                </td>
              </tr>
              <tr className="border-b border-divider">
                <td className="py-2 pr-4 opacity-60">Access Mode</td>
                <td className="py-2">{detail.access_mode}</td>
              </tr>
              <tr>
                <td className="py-2 pr-4 opacity-60">Created</td>
                <td className="py-2">{formatDateTime(detail.created_at)}</td>
              </tr>
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

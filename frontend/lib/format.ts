// Shared display-formatting helpers for admin/owner stat displays.
// See docs/decisions/2026-08-15-shared-format-helpers.md for why this
// module exists rather than duplicating formatting inline per page.

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return '0 MB';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  );
  const value = bytes / Math.pow(1024, exponent);
  return `${value.toFixed(value >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
}

// Matches the en-IN date convention already used across the admin/owner UI
// (see app/admin/page.tsx, components/EventCard.tsx) but includes a time
// component since this is used for full timestamps (e.g. last_activity_at),
// not date-only fields like event_date.
export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`;
}

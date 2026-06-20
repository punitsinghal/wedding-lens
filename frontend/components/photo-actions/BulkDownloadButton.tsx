'use client';

import { useState } from 'react';
import { downloadZip, downloadFavouritesZip } from '@/lib/api';

const ZIP_CAP = 200;

interface BulkDownloadButtonProps {
  source: 'search' | 'favourites';
  eventId: string;
  photoIds?: string[]; // required for source="search"
  disabled?: boolean;
}

export default function BulkDownloadButton({
  source,
  eventId,
  photoIds = [],
  disabled = false,
}: BulkDownloadButtonProps) {
  const [isDownloading, setIsDownloading] = useState(false);

  if (source === 'favourites' && disabled) return null;

  async function handleDownload() {
    setIsDownloading(true);
    try {
      if (source === 'search') {
        await downloadZip(eventId, photoIds.slice(0, ZIP_CAP));
      } else {
        await downloadFavouritesZip(eventId);
      }
    } catch {
      // download errors are silent — the browser will show nothing
    } finally {
      setIsDownloading(false);
    }
  }

  const capped = source === 'search' && photoIds.length > ZIP_CAP;

  return (
    <div className="flex flex-col items-end gap-1">
      {capped && (
        <p className="text-xs text-gray-400">Only the first {ZIP_CAP} photos will be included.</p>
      )}
      <button
        type="button"
        onClick={handleDownload}
        disabled={isDownloading || disabled}
        className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium bg-gray-900 text-white rounded-full hover:bg-gray-700 disabled:opacity-50 transition-colors"
      >
        <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
        </svg>
        {isDownloading ? 'Preparing...' : 'Download all as ZIP'}
      </button>
    </div>
  );
}

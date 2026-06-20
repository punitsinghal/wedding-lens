'use client';

import { useState } from 'react';
import { generateShareLink } from '@/lib/api';

interface ShareButtonProps {
  eventId: string;
  photoId: string;
  className?: string;
}

export default function ShareButton({ eventId, photoId, className = '' }: ShareButtonProps) {
  const [copied, setCopied] = useState(false);

  async function handleShare(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      const { share_url } = await generateShareLink(eventId, photoId);
      await navigator.clipboard.writeText(share_url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // silently ignore (clipboard may be blocked in some contexts)
    }
  }

  return (
    <button
      type="button"
      onClick={handleShare}
      aria-label="Copy share link"
      className={`p-1.5 rounded-full bg-black/40 hover:bg-black/60 transition-colors relative ${className}`}
    >
      {copied ? (
        <svg className="h-4 w-4 text-green-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
        </svg>
      ) : (
        <svg className="h-4 w-4 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 1 0 0 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186 9.566-5.314m-9.566 7.5 9.566 5.314m0 0a2.25 2.25 0 1 0 3.935 2.186 2.25 2.25 0 0 0-3.935-2.186Zm0-12.814a2.25 2.25 0 1 0 3.933-2.185 2.25 2.25 0 0 0-3.933 2.185Z" />
        </svg>
      )}
    </button>
  );
}

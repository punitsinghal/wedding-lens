'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useParams } from 'next/navigation';
import Link from 'next/link';
import { getEventBySlug } from '@/lib/api';
import {
  isGuestAuthenticated,
  getGuestToken,
  setGuestToken as persistGuestToken,
} from '@/lib/auth';
import SelfieUpload from '@/components/search/SelfieUpload';
import SearchResults from '@/components/search/SearchResults';
import SearchError from '@/components/search/SearchError';
import type { SearchResultItem } from '@/components/search/SelfieUpload';

// Inner component — useParams requires Suspense wrapper
function SearchContent() {
  const router = useRouter();
  const params = useParams();
  const slug = params.slug as string;

  const [eventId, setEventId] = useState('');
  const [guestToken, setGuestTokenState] = useState('');
  const [isChecking, setIsChecking] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [results, setResults] = useState<SearchResultItem[] | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Auth check on mount
  // ---------------------------------------------------------------------------
  useEffect(() => {
    getEventBySlug(slug)
      .then((ev) => {
        if (ev.access_mode !== 'public' && !isGuestAuthenticated(ev.id)) {
          router.replace(`/g/${slug}`);
          return;
        }
        setEventId(ev.id);
        setGuestTokenState(getGuestToken(ev.id) ?? '');
        setIsChecking(false);
      })
      .catch(() => {
        router.replace(`/g/${slug}`);
      });
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, router]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  if (isChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center gap-3">
          <Link
            href={`/g/${slug}/gallery`}
            className="text-gray-500 hover:text-gray-900 transition-colors"
            aria-label="Back to gallery"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={1.5}
              stroke="currentColor"
              className="h-5 w-5"
              aria-hidden="true"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18"
              />
            </svg>
          </Link>
          <h1 className="text-xl font-bold text-gray-900">Find my photos</h1>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-6xl mx-auto">
        {errorCode ? (
          <SearchError
            code={errorCode}
            onRetry={() => {
              setErrorCode(null);
              setResults(null);
            }}
          />
        ) : results ? (
          <SearchResults
            results={results}
            eventId={eventId}
            onRetry={() => setResults(null)}
          />
        ) : (
          <SelfieUpload
            eventId={eventId}
            guestToken={guestToken}
            isUploading={isUploading}
            onUploadStart={() => setIsUploading(true)}
            onUploadEnd={() => setIsUploading(false)}
            onResults={(res) => {
              setResults(res);
              setErrorCode(null);
            }}
            onError={(code) => {
              setErrorCode(code);
              setResults(null);
            }}
            onTokenRefresh={(newToken) => {
              persistGuestToken(eventId, newToken);
              setGuestTokenState(newToken);
            }}
          />
        )}
      </main>
    </div>
  );
}

export default function GuestSearchPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          <p className="text-gray-400 text-sm">Loading...</p>
        </div>
      }
    >
      <SearchContent />
    </Suspense>
  );
}

'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useParams } from 'next/navigation';
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
import PageLoading from '@/components/PageLoading';
import GuestHomeLink from '@/components/guest/GuestHomeLink';

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
          setIsChecking(false);
          return;
        }
        setEventId(ev.id);
        setGuestTokenState(getGuestToken(ev.id) ?? '');
        setIsChecking(false);
      })
      .catch(() => {
        router.replace(`/g/${slug}`);
        setIsChecking(false);
      });
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, router]);

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  if (isChecking) {
    return <PageLoading />;
  }

  return (
    <div className="min-h-screen bg-bg">
      {/* Header */}
      <header className="bg-bg border-b border-divider px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center gap-3">
          <GuestHomeLink slug={slug} />
          <h1 className="text-xl">Find my photos</h1>
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
      fallback={<PageLoading />}
    >
      <SearchContent />
    </Suspense>
  );
}

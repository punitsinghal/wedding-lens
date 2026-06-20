'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getGuestToken, setGuestToken, isGuestAuthenticated } from '@/lib/auth';
import SelfieUpload from '@/components/search/SelfieUpload';
import SearchResults from '@/components/search/SearchResults';
import SearchError from '@/components/search/SearchError';
import type { SearchResultItem } from '@/components/search/SelfieUpload';

type SearchState = 'idle' | 'uploading' | 'results' | 'error';

export default function SearchPage() {
  const params = useParams();
  const router = useRouter();
  const eventId = params.eventId as string;

  const [guestToken, setGuestTokenState] = useState<string>('');
  const [searchState, setSearchState] = useState<SearchState>('idle');
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [errorCode, setErrorCode] = useState<string>('');

  // Auth guard: redirect to home if no valid guest token for this event
  useEffect(() => {
    if (!isGuestAuthenticated(eventId)) {
      router.replace('/');
      return;
    }
    const token = getGuestToken(eventId);
    if (token) setGuestTokenState(token);
  }, [eventId, router]);

  function handleTokenRefresh(newToken: string) {
    setGuestToken(eventId, newToken);
    setGuestTokenState(newToken);
  }

  function handleResults(newResults: SearchResultItem[]) {
    setResults(newResults);
    setSearchState('results');
  }

  function handleError(code: string) {
    setErrorCode(code);
    setSearchState('error');
  }

  function handleRetry() {
    setResults([]);
    setErrorCode('');
    setSearchState('idle');
  }

  function handleUploadStart() {
    // Clear previous results immediately so stale data is never visible during upload
    setResults([]);
    setErrorCode('');
    setSearchState('uploading');
  }

  function handleUploadEnd() {
    // State transitions to 'results' or 'error' are handled by handleResults/handleError
  }

  const isUploading = searchState === 'uploading';

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-4">
        <div className="max-w-2xl mx-auto">
          <h1 className="text-xl font-bold text-gray-900">Find Your Photos</h1>
        </div>
      </header>

      <main className="max-w-2xl mx-auto">
        {(searchState === 'idle' || searchState === 'uploading') && (
          <SelfieUpload
            eventId={eventId}
            guestToken={guestToken}
            onResults={handleResults}
            onError={handleError}
            onTokenRefresh={handleTokenRefresh}
            isUploading={isUploading}
            onUploadStart={handleUploadStart}
            onUploadEnd={handleUploadEnd}
          />
        )}

        {searchState === 'results' && (
          <SearchResults
            results={results}
            eventId={eventId}
            onRetry={handleRetry}
          />
        )}

        {searchState === 'error' && (
          <SearchError code={errorCode} onRetry={handleRetry} />
        )}
      </main>
    </div>
  );
}

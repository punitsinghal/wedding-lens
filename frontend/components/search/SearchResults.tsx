'use client';

import { useEffect, useState } from 'react';
import { guestFetchBlob } from '@/lib/api';
import type { SearchResultItem } from './SelfieUpload';

interface SearchResultsProps {
  results: SearchResultItem[];
  eventId: string;
  onRetry: () => void;
}

interface ResultCardProps {
  result: SearchResultItem;
  eventId: string;
}

function ResultCard({ result, eventId }: ResultCardProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    guestFetchBlob(eventId, result.thumbnail_url)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      })
      .catch(() => {
        // leave blobUrl as null — placeholder stays visible
      });

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [result.photo_id, result.thumbnail_url, eventId]);

  return (
    <div className="relative aspect-square w-full overflow-hidden rounded-sm bg-gray-200">
      {blobUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={blobUrl}
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 bg-gray-200 animate-pulse" />
      )}
    </div>
  );
}

export default function SearchResults({ results, eventId, onRetry }: SearchResultsProps) {
  return (
    <div className="px-4 py-6">
      {results.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <svg
            className="h-12 w-12 text-gray-300 mb-4"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 0 0 1.5-1.5V6a1.5 1.5 0 0 0-1.5-1.5H3.75A1.5 1.5 0 0 0 2.25 6v12a1.5 1.5 0 0 0 1.5 1.5Zm10.5-11.25h.008v.008h-.008V8.25Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z"
            />
          </svg>
          <p className="text-gray-600 font-medium">No photos found</p>
          <p className="mt-1 text-sm text-gray-400">
            We couldn&apos;t find any photos matching your face. Try a clearer selfie.
          </p>
          <button
            onClick={onRetry}
            className="mt-6 px-5 py-2 text-sm font-medium bg-blue-600 text-white rounded-full hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
          >
            Try another photo
          </button>
        </div>
      ) : (
        <>
          <p className="text-sm text-gray-500 mb-4">
            Found {results.length} photo{results.length === 1 ? '' : 's'} with you in them.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5 mb-6">
            {results.map((result) => (
              <ResultCard key={result.photo_id} result={result} eventId={eventId} />
            ))}
          </div>
          <div className="flex justify-center">
            <button
              onClick={onRetry}
              className="px-5 py-2 text-sm font-medium bg-gray-900 text-white rounded-full hover:bg-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-900 transition-colors"
            >
              Try another photo
            </button>
          </div>
        </>
      )}
    </div>
  );
}

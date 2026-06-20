'use client';

import { useRef, ChangeEvent } from 'react';
import { getGuestToken } from '@/lib/auth';

export interface SearchResultItem {
  photo_id: string;
  thumbnail_url: string;
}

const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB

function baseUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
}

export interface SelfieUploadProps {
  eventId: string;
  guestToken: string;
  onResults: (results: SearchResultItem[]) => void;
  onError: (code: string) => void;
  onTokenRefresh: (newToken: string) => void;
  isUploading: boolean;
  onUploadStart: () => void;
  onUploadEnd: () => void;
}

export default function SelfieUpload({
  eventId,
  guestToken,
  onResults,
  onError,
  onTokenRefresh,
  isUploading,
  onUploadStart,
  onUploadEnd,
}: SelfieUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    // Client-side file size check
    if (file.size > MAX_FILE_SIZE_BYTES) {
      onError('file_too_large');
      // Reset the input so the same file can be re-selected after correction
      if (inputRef.current) inputRef.current.value = '';
      return;
    }

    onUploadStart();

    try {
      const formData = new FormData();
      formData.append('selfie', file);

      const token = guestToken || getGuestToken(eventId);
      const headers: Record<string, string> = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch(
        `${baseUrl()}/api/v1/events/${eventId}/search`,
        {
          method: 'POST',
          headers,
          body: formData,
        }
      );

      // Always try to read the refreshed token header
      const refreshedToken = response.headers.get('X-Guest-Token');
      if (refreshedToken) {
        onTokenRefresh(refreshedToken);
      }

      if (!response.ok) {
        let detail = 'unknown_error';
        try {
          const body = (await response.json()) as { detail?: string };
          if (typeof body.detail === 'string') detail = body.detail;
        } catch {
          // ignore parse errors
        }
        onError(detail);
        return;
      }

      const data = (await response.json()) as { results: SearchResultItem[] };
      onResults(data.results);
    } catch {
      onError('network_error');
    } finally {
      onUploadEnd();
      if (inputRef.current) inputRef.current.value = '';
    }
  }

  return (
    <div className="flex flex-col items-center gap-6 px-4 py-8">
      <div className="text-center">
        <h2 className="text-lg font-semibold text-gray-900">Find your photos</h2>
        <p className="mt-1 text-sm text-gray-500">
          Upload a clear selfie and we&apos;ll find all the photos you appear in.
        </p>
      </div>

      <label
        htmlFor="selfie-input"
        className={`flex flex-col items-center justify-center w-full max-w-xs border-2 border-dashed rounded-xl px-6 py-10 cursor-pointer transition-colors ${
          isUploading
            ? 'border-gray-300 bg-gray-50 cursor-not-allowed'
            : 'border-blue-400 bg-blue-50 hover:bg-blue-100'
        }`}
      >
        {isUploading ? (
          <>
            <svg
              className="animate-spin h-8 w-8 text-blue-500 mb-3"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8v8H4z"
              />
            </svg>
            <span className="text-sm text-gray-500">Searching...</span>
          </>
        ) : (
          <>
            <svg
              className="h-8 w-8 text-blue-400 mb-3"
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
                d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z"
              />
            </svg>
            <span className="text-sm font-medium text-blue-600">Take or upload a selfie</span>
            <span className="mt-1 text-xs text-gray-400">JPEG or PNG, max 20 MB</span>
          </>
        )}
      </label>

      <input
        ref={inputRef}
        id="selfie-input"
        type="file"
        accept="image/jpeg,image/png"
        capture="user"
        disabled={isUploading}
        onChange={handleFileChange}
        className="sr-only"
      />
    </div>
  );
}

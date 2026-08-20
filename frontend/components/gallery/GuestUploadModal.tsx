'use client';

import { useState, ChangeEvent } from 'react';
import { uploadGuestPhoto } from '@/lib/api';
import { getGuestToken, setGuestToken } from '@/lib/auth';

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png'];
const SESSION_CAP = 20;
const CONCURRENCY = 3;

type FileStatus = 'pending' | 'uploading' | 'success' | 'error';

interface FileEntry {
  file: File;
  status: FileStatus;
  message?: string;
}

interface GuestUploadModalProps {
  eventId: string;
  onClose: () => void;
}

export default function GuestUploadModal({ eventId, onClose }: GuestUploadModalProps) {
  const [displayName, setDisplayName] = useState('');
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [capMessage, setCapMessage] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [done, setDone] = useState(false);

  function validateFile(file: File): string | null {
    if (!ALLOWED_TYPES.includes(file.type)) return 'Unsupported format';
    if (file.size > MAX_FILE_SIZE_BYTES) return 'File too large';
    return null;
  }

  function handleFilesSelected(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (files.length === 0) return;

    let capped = files;
    if (files.length > SESSION_CAP) {
      capped = files.slice(0, SESSION_CAP);
      setCapMessage(
        `A single upload session is capped at ${SESSION_CAP} photos — only the first ${SESSION_CAP} were selected.`
      );
    } else {
      setCapMessage('');
    }

    const nextEntries: FileEntry[] = capped.map((file) => {
      const error = validateFile(file);
      return error
        ? { file, status: 'error' as const, message: error }
        : { file, status: 'pending' as const };
    });
    setEntries(nextEntries);
    setDone(false);
  }

  async function handleUpload() {
    if (isUploading || entries.length === 0) return;
    setIsUploading(true);

    const toUpload = entries
      .map((entry, index) => ({ entry, index }))
      .filter(({ entry }) => entry.status === 'pending');

    let cursor = 0;
    async function worker() {
      while (cursor < toUpload.length) {
        const current = toUpload[cursor];
        cursor += 1;
        const { entry, index } = current;

        setEntries((prev) => {
          const next = [...prev];
          next[index] = { ...next[index], status: 'uploading' };
          return next;
        });

        try {
          const token = getGuestToken(eventId) ?? '';
          await uploadGuestPhoto(
            eventId,
            token,
            entry.file,
            displayName.trim() || undefined,
            (newToken) => setGuestToken(eventId, newToken)
          );
          setEntries((prev) => {
            const next = [...prev];
            next[index] = { ...next[index], status: 'success' };
            return next;
          });
        } catch (err: unknown) {
          const apiErr = err as { detail?: string };
          setEntries((prev) => {
            const next = [...prev];
            next[index] = {
              ...next[index],
              status: 'error',
              message: apiErr?.detail ?? 'Upload failed',
            };
            return next;
          });
        }
      }
    }

    const workers = Array.from({ length: Math.min(CONCURRENCY, toUpload.length) }, () => worker());
    await Promise.all(workers);

    setIsUploading(false);
    setDone(true);
  }

  function handleClose() {
    setEntries([]);
    setDisplayName('');
    setCapMessage('');
    setDone(false);
    onClose();
  }

  const totalCount = entries.length;
  const successCount = entries.filter((e) => e.status === 'success').length;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/50"
      role="dialog"
      aria-modal="true"
      aria-labelledby="guest-upload-title"
    >
      <div className="w-full sm:max-w-md bg-surface rounded-t-[36px] sm:rounded-[36px] shadow-lg p-6 pb-8 sm:pb-6 max-h-[92vh] overflow-y-auto">
        <div className="w-11 h-1.5 rounded-full bg-neutral-300 mx-auto mb-4 sm:hidden" />

        <div className="flex items-center justify-between mb-1">
          <h2 id="guest-upload-title" className="text-xl">
            Upload your photos
          </h2>
          <button onClick={handleClose} className="btn btn-icon btn-ghost -mr-1.5" aria-label="Close">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {done ? (
          <div className="py-4 text-center">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 text-accent-2-600 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <p className="text-base mb-1">
              {successCount} of {totalCount} photos received.
            </p>
            <p className="text-sm opacity-70">They&apos;ll appear in the gallery once processed.</p>
            <button onClick={handleClose} className="btn btn-primary mt-5">
              Done
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm opacity-70">
              Take a new photo or choose from your gallery — no account needed.
            </p>

            <div className="field">
              <label htmlFor="guest-upload-display-name">Your name (optional)</label>
              <input
                id="guest-upload-display-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                maxLength={100}
                className="input"
                placeholder="e.g. Priya Sharma"
              />
              <p className="mt-1 text-xs opacity-50">Shown on your photos so guests know who took them.</p>
            </div>

            <div className="field">
              <label htmlFor="guest-upload-input">Photos</label>
              <input
                id="guest-upload-input"
                type="file"
                accept="image/jpeg,image/png"
                multiple
                capture="environment"
                disabled={isUploading}
                onChange={handleFilesSelected}
                className="input"
              />
            </div>

            {capMessage && (
              <p className="text-xs text-amber-700 bg-amber-50 border border-amber-300 rounded-lg px-3 py-2">
                {capMessage}
              </p>
            )}

            {entries.length > 0 && (
              <ul className="space-y-1.5 max-h-48 overflow-y-auto">
                {entries.map((entry, i) => (
                  <li key={`${entry.file.name}-${i}`} className="flex items-center justify-between text-sm gap-2">
                    <span className="truncate flex-1">{entry.file.name}</span>
                    <span
                      className={
                        entry.status === 'error'
                          ? 'text-[#b3261e] text-xs shrink-0'
                          : entry.status === 'success'
                          ? 'text-accent-2-600 text-xs shrink-0'
                          : 'opacity-50 text-xs shrink-0'
                      }
                    >
                      {entry.status === 'pending' && 'Ready'}
                      {entry.status === 'uploading' && 'Uploading...'}
                      {entry.status === 'success' && 'Uploaded'}
                      {entry.status === 'error' && entry.message}
                    </span>
                  </li>
                ))}
              </ul>
            )}

            <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-3 pt-1">
              <button type="button" onClick={handleClose} className="btn btn-ghost" disabled={isUploading}>
                Cancel
              </button>
              <button
                type="button"
                onClick={handleUpload}
                disabled={isUploading || entries.every((e) => e.status !== 'pending')}
                className="btn btn-primary btn-block sm:w-auto"
              >
                {isUploading ? 'Uploading...' : 'Upload'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

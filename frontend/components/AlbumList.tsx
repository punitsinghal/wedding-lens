'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Album, AlbumCreateRequest, AlbumVisibility, CeremonyCategory } from '@/types/api';
import { createAlbum, updateAlbum, deleteAlbum } from '@/lib/api';
import ConfirmDialog from './ConfirmDialog';

const CEREMONY_CATEGORIES: CeremonyCategory[] = [
  'Ceremony',
  'Sangeet',
  'Mehendi',
  'Haldi',
  'Reception',
  'Family Photos',
];

export const MAX_ALBUMS = 10;

interface Props {
  eventId: string;
  initialAlbums: Album[];
}

function PlusIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path d="M6 1v10M1 6h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function TrashIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M3 5h14M8 5V3.5A1.5 1.5 0 019.5 2h1A1.5 1.5 0 0112 3.5V5m-7 0v11a1.5 1.5 0 001.5 1.5h5a1.5 1.5 0 001.5-1.5V5M8.5 8.5v6M11.5 8.5v6"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function AlbumList({ eventId, initialAlbums }: Props) {
  const [albums, setAlbums] = useState<Album[]>(initialAlbums);
  const [error, setError] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  // Create form state
  const [newName, setNewName] = useState('');
  const [newCategory, setNewCategory] = useState<CeremonyCategory | ''>('');

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editCategory, setEditCategory] = useState<CeremonyCategory | ''>('');

  // Delete confirm
  const [deletingAlbum, setDeletingAlbum] = useState<Album | null>(null);

  // Visibility toggle
  const [togglingId, setTogglingId] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setError('');
    try {
      const data: AlbumCreateRequest = {
        name: newName.trim(),
        ...(newCategory ? { ceremony_category: newCategory as CeremonyCategory } : {}),
      };
      const album = await createAlbum(eventId, data);
      setAlbums((prev) => [...prev, album]);
      setNewName('');
      setNewCategory('');
      setIsCreating(false);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Failed to create album.');
    }
  }

  function startEdit(album: Album) {
    setEditingId(album.id);
    setEditName(album.name);
    setEditCategory(album.ceremony_category ?? '');
  }

  async function handleUpdate(albumId: string, e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const updated = await updateAlbum(eventId, albumId, {
        name: editName.trim() || undefined,
        ceremony_category: editCategory ? (editCategory as CeremonyCategory) : null,
      });
      setAlbums((prev) => prev.map((a) => (a.id === albumId ? updated : a)));
      setEditingId(null);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Failed to update album.');
    }
  }

  async function handleToggleVisibility(album: Album) {
    setTogglingId(album.id);
    const next: AlbumVisibility = album.visibility === 'public' ? 'private' : 'public';
    try {
      const updated = await updateAlbum(eventId, album.id, { visibility: next });
      setAlbums((prev) => prev.map((a) => (a.id === album.id ? updated : a)));
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Failed to update album visibility.');
    } finally {
      setTogglingId(null);
    }
  }

  async function handleDelete(album: Album) {
    setError('');
    try {
      await deleteAlbum(eventId, album.id);
      setAlbums((prev) => prev.filter((a) => a.id !== album.id));
      setDeletingAlbum(null);
    } catch (err: unknown) {
      const apiErr = err as { detail?: string };
      setError(apiErr?.detail ?? 'Failed to delete album.');
      setDeletingAlbum(null);
    }
  }

  return (
    <div>
      {albums.length < MAX_ALBUMS && !isCreating && (
        <div className="flex justify-end mb-4">
          <button onClick={() => setIsCreating(true)} className="btn btn-primary">
            <PlusIcon className="w-3 h-3" />
            New Album
          </button>
        </div>
      )}

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md text-sm bg-[#fdeceb] text-[#8c2018] border border-[#f3c6c2]">
          {error}
        </div>
      )}

      {isCreating && (
        <form onSubmit={handleCreate} className="card elev-sm bg-accent-100 mb-4">
          <h3 className="card-title">New Album</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="field">
              <label>
                Album Name <span className="text-accent">*</span>
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
                className="input"
                placeholder="e.g. Pre-Wedding Shoot"
              />
            </div>
            <div className="field">
              <label>
                Ceremony Category <span className="opacity-60">(optional)</span>
              </label>
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value as CeremonyCategory | '')}
                className="input"
              >
                <option value="">— None —</option>
                {CEREMONY_CATEGORIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button type="submit" className="btn btn-primary">
              Create
            </button>
            <button
              type="button"
              onClick={() => {
                setIsCreating(false);
                setNewName('');
                setNewCategory('');
              }}
              className="btn btn-secondary"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {albums.length === 0 && !isCreating ? (
        <div className="py-10 text-center text-sm opacity-60 rounded-[32px] border border-dashed border-divider">
          No albums yet. Create one to organise photos.
        </div>
      ) : (
        <ul className="space-y-3">
          {albums.map((album) =>
            editingId === album.id ? (
              <li key={album.id}>
                <form onSubmit={(e) => handleUpdate(album.id, e)} className="card elev-sm bg-accent-100">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div className="field">
                      <label>Album Name</label>
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        required
                        className="input"
                      />
                    </div>
                    <div className="field">
                      <label>Ceremony Category</label>
                      <select
                        value={editCategory}
                        onChange={(e) => setEditCategory(e.target.value as CeremonyCategory | '')}
                        className="input"
                      >
                        <option value="">— None —</option>
                        {CEREMONY_CATEGORIES.map((c) => (
                          <option key={c} value={c}>
                            {c}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                  <div className="flex gap-2 pt-1">
                    <button type="submit" className="btn btn-primary">
                      Save
                    </button>
                    <button type="button" onClick={() => setEditingId(null)} className="btn btn-secondary">
                      Cancel
                    </button>
                  </div>
                </form>
              </li>
            ) : (
              <li key={album.id} className="card elev-sm flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-12 h-12 rounded-full bg-neutral-200 flex-none" />
                  <div className="min-w-0">
                    <p className="card-title truncate">{album.name}</p>
                    <p className="card-meta mt-0.5">
                      {album.ceremony_category ?? 'Uncategorized'} ·{' '}
                      {album.cover_photo_id ? 'Cover set' : 'No cover yet'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2 flex-none flex-wrap justify-end">
                  <button
                    type="button"
                    onClick={() => handleToggleVisibility(album)}
                    disabled={togglingId === album.id}
                    title={
                      album.visibility === 'private'
                        ? 'Make public (visible to guests)'
                        : 'Make private (hidden from guests)'
                    }
                    className={`tag border-0 cursor-pointer disabled:opacity-50 ${
                      album.visibility === 'public' ? 'tag-accent-2' : 'tag-neutral'
                    }`}
                  >
                    {album.visibility === 'public' ? 'Public' : 'Private'}
                  </button>
                  <Link href={`/events/${eventId}/albums/${album.id}`} className="btn btn-secondary text-xs px-3 py-1.5">
                    Photos
                  </Link>
                  <button type="button" onClick={() => startEdit(album)} className="btn btn-secondary text-xs px-3 py-1.5">
                    Rename
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeletingAlbum(album)}
                    className="btn btn-icon btn-secondary"
                    aria-label="Delete album"
                    title="Delete album"
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                </div>
              </li>
            )
          )}
        </ul>
      )}

      {albums.length >= MAX_ALBUMS && (
        <p className="mt-3 text-xs px-3 py-2 rounded-md bg-accent-100 text-accent-800 border border-accent-200">
          Maximum of {MAX_ALBUMS} albums per event reached.
        </p>
      )}

      <ConfirmDialog
        isOpen={deletingAlbum !== null}
        title="Delete Album"
        message={`Delete album "${deletingAlbum?.name}"? Photos in this album will be moved to uncategorized state.`}
        confirmText="DELETE"
        confirmLabel="Delete Album"
        onConfirm={() => deletingAlbum && handleDelete(deletingAlbum)}
        onCancel={() => setDeletingAlbum(null)}
        destructive
      />
    </div>
  );
}

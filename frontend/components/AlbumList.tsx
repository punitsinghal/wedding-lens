'use client';

import { useState } from 'react';
import Link from 'next/link';
import type { Album, AlbumCreateRequest, CeremonyCategory } from '@/types/api';
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

const MAX_ALBUMS = 10;

interface Props {
  eventId: string;
  initialAlbums: Album[];
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
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-gray-900">
          Albums{' '}
          <span className="text-sm font-normal text-gray-500">
            {albums.length} / {MAX_ALBUMS}
          </span>
        </h2>
        {albums.length < MAX_ALBUMS && !isCreating && (
          <button
            onClick={() => setIsCreating(true)}
            className="text-sm bg-blue-600 text-white px-3 py-1.5 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            + New Album
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700">
          {error}
        </div>
      )}

      {isCreating && (
        <form
          onSubmit={handleCreate}
          className="mb-4 p-4 border border-blue-200 bg-blue-50 rounded-lg"
        >
          <h3 className="text-sm font-semibold text-gray-800 mb-3">New Album</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Album Name <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                required
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="e.g. Pre-Wedding Shoot"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">
                Ceremony Category <span className="text-gray-400">(optional)</span>
              </label>
              <select
                value={newCategory}
                onChange={(e) => setNewCategory(e.target.value as CeremonyCategory | '')}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
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
          <div className="flex gap-2 mt-3">
            <button
              type="submit"
              className="text-sm bg-blue-600 text-white px-4 py-1.5 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              Create
            </button>
            <button
              type="button"
              onClick={() => {
                setIsCreating(false);
                setNewName('');
                setNewCategory('');
              }}
              className="text-sm text-gray-600 px-4 py-1.5 rounded-md border border-gray-300 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400"
            >
              Cancel
            </button>
          </div>
        </form>
      )}

      {albums.length === 0 && !isCreating ? (
        <p className="text-sm text-gray-500 py-8 text-center border border-dashed border-gray-200 rounded-lg">
          No albums yet. Create one to organise photos.
        </p>
      ) : (
        <ul className="space-y-2">
          {albums.map((album) =>
            editingId === album.id ? (
              <li
                key={album.id}
                className="border border-yellow-200 bg-yellow-50 rounded-lg p-3"
              >
                <form onSubmit={(e) => handleUpdate(album.id, e)}>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      required
                      className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <select
                      value={editCategory}
                      onChange={(e) =>
                        setEditCategory(e.target.value as CeremonyCategory | '')
                      }
                      className="border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">— None —</option>
                      {CEREMONY_CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>

                  </div>
                  <div className="flex gap-2 mt-2">
                    <button
                      type="submit"
                      className="text-sm bg-blue-600 text-white px-3 py-1 rounded-md hover:bg-blue-700"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="text-sm text-gray-600 px-3 py-1 rounded-md border border-gray-300 hover:bg-gray-50"
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              </li>
            ) : (
              <li
                key={album.id}
                className="flex items-center justify-between border border-gray-200 rounded-lg px-4 py-3 bg-white hover:bg-gray-50"
              >
                <div>
                  <span className="text-sm font-medium text-gray-900">{album.name}</span>
                  {album.ceremony_category && (
                    <span className="ml-2 text-xs text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
                      {album.ceremony_category}
                    </span>
                  )}
                  {album.cover_photo_id && (
                    <span className="ml-2 text-xs text-blue-500 bg-blue-50 px-2 py-0.5 rounded-full">
                      Cover set
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <Link
                    href={`/events/${eventId}/albums/${album.id}`}
                    className="text-xs text-gray-600 hover:text-gray-800 font-medium"
                  >
                    Photos
                  </Link>
                  <button
                    onClick={() => startEdit(album)}
                    className="text-xs text-blue-600 hover:text-blue-800 font-medium"
                  >
                    Rename
                  </button>
                  <button
                    onClick={() => setDeletingAlbum(album)}
                    className="text-xs text-red-600 hover:text-red-800 font-medium"
                  >
                    Delete
                  </button>
                </div>
              </li>
            )
          )}
        </ul>
      )}

      {albums.length >= MAX_ALBUMS && (
        <p className="mt-3 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
          Maximum of {MAX_ALBUMS} albums per event reached.
        </p>
      )}

      <ConfirmDialog
        isOpen={deletingAlbum !== null}
        title="Delete Album"
        message={`Delete album "${deletingAlbum?.name}"? Photos in this album will be moved to uncategorized state.`}
        confirmLabel="Delete Album"
        onConfirm={() => deletingAlbum && handleDelete(deletingAlbum)}
        onCancel={() => setDeletingAlbum(null)}
        destructive
      />
    </div>
  );
}

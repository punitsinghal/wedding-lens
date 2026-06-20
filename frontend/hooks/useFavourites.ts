'use client';

import { useState, useEffect, useCallback } from 'react';
import { getFavourites, addFavourite, removeFavourite } from '@/lib/api';

export function useFavourites(eventId: string) {
  const [favouriteIds, setFavouriteIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!eventId) return;
    setIsLoading(true);
    getFavourites(eventId)
      .then((res) => setFavouriteIds(new Set(res.photos.map((p) => p.photo_id))))
      .catch(() => {/* leave empty set */})
      .finally(() => setIsLoading(false));
  }, [eventId]);

  const toggle = useCallback(
    async (photoId: string) => {
      const wasFavourited = favouriteIds.has(photoId);
      // Optimistic update
      setFavouriteIds((prev) => {
        const next = new Set(prev);
        if (wasFavourited) next.delete(photoId);
        else next.add(photoId);
        return next;
      });
      try {
        if (wasFavourited) {
          await removeFavourite(eventId, photoId);
        } else {
          await addFavourite(eventId, photoId);
        }
      } catch {
        // Revert on error
        setFavouriteIds((prev) => {
          const next = new Set(prev);
          if (wasFavourited) next.add(photoId);
          else next.delete(photoId);
          return next;
        });
      }
    },
    [eventId, favouriteIds]
  );

  return {
    favouriteIds,
    isFavourited: (photoId: string) => favouriteIds.has(photoId),
    toggle,
    isLoading,
  };
}

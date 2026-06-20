'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { getFavourites, addFavourite, removeFavourite } from '@/lib/api';
import type { FavouritePhoto } from '@/types/api';

export function useFavourites(eventId: string) {
  const [photos, setPhotos] = useState<FavouritePhoto[]>([]);
  const [favouriteIds, setFavouriteIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!eventId) return;
    setIsLoading(true);
    getFavourites(eventId)
      .then((res) => {
        setPhotos(res.photos);
        setFavouriteIds(new Set(res.photos.map((p) => p.photo_id)));
      })
      .catch(() => {/* leave empty set */})
      .finally(() => setIsLoading(false));
  }, [eventId]);

  const favouriteIdsRef = useRef<Set<string>>(favouriteIds);
  useEffect(() => {
    favouriteIdsRef.current = favouriteIds;
  }, [favouriteIds]);

  const toggle = useCallback(
    async (photoId: string) => {
      const wasFavourited = favouriteIdsRef.current.has(photoId);
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
        setFavouriteIds((prev) => {
          const next = new Set(prev);
          if (wasFavourited) next.add(photoId);
          else next.delete(photoId);
          return next;
        });
      }
    },
    [eventId]  // no favouriteIds — reads current value via ref
  );

  return {
    photos,
    favouriteIds,
    isFavourited: (photoId: string) => favouriteIds.has(photoId),
    toggle,
    isLoading,
  };
}

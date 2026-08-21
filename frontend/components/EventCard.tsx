'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ownerFetchBlob } from '@/lib/api';
import type { Event } from '@/types/api';
import StatusBadge from './StatusBadge';

interface Props {
  event: Event;
}

export default function EventCard({ event }: Props) {
  const [coverUrl, setCoverUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!event.cover_photo_id) return;

    let objectUrl: string | null = null;
    let cancelled = false;

    ownerFetchBlob(`/api/v1/events/${event.id}/cover-thumbnail`)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setCoverUrl(objectUrl);
      })
      .catch(() => {
        // leave coverUrl as null — placeholder stays visible
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [event.id, event.cover_photo_id]);

  const formattedDate = new Date(event.event_date).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="card elev-sm">
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded-md bg-neutral-200">
        {coverUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={coverUrl}
            alt=""
            className="absolute inset-0 w-full h-full object-cover"
          />
        )}
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={event.status} />
      </div>

      <div className="min-w-0">
        <h3 className="card-title text-[21px] truncate">{event.name}</h3>
        <p className="text-sm opacity-70 truncate mt-0.5">
          {event.bride_name} &amp; {event.groom_name}
        </p>
        <p className="card-meta mt-1">{formattedDate}</p>
      </div>

      <div className="flex items-center gap-2 flex-wrap pt-1">
        <Link href={`/events/${event.id}`} className="btn btn-secondary text-xs px-3 py-1.5">
          Edit
        </Link>
        <Link href={`/events/${event.id}/albums`} className="btn btn-secondary text-xs px-3 py-1.5">
          Albums
        </Link>
        <Link href={`/events/${event.id}/qr`} className="btn btn-secondary text-xs px-3 py-1.5">
          QR Code
        </Link>
      </div>
    </div>
  );
}

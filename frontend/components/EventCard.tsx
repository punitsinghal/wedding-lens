import Link from 'next/link';
import type { Event } from '@/types/api';
import StatusBadge from './StatusBadge';

interface Props {
  event: Event;
}

export default function EventCard({ event }: Props) {
  const formattedDate = new Date(event.event_date).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="card elev-sm">
      <div className="aspect-[4/3] w-full rounded-md bg-neutral-200" />

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

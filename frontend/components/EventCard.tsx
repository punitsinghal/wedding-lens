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
    <div className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{event.name}</h3>
          <p className="text-sm text-gray-500 mt-0.5">
            {event.bride_name} &amp; {event.groom_name}
          </p>
          <p className="text-xs text-gray-400 mt-1">{formattedDate}</p>
          <p className="text-xs text-gray-400 font-mono mt-0.5">/{event.slug}</p>
        </div>
        <StatusBadge status={event.status} />
      </div>

      <div className="mt-4 flex items-center gap-3 flex-wrap">
        <Link
          href={`/events/${event.id}`}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          Edit
        </Link>
        <Link
          href={`/events/${event.id}/albums`}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          Albums
        </Link>
        <Link
          href={`/events/${event.id}/qr`}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          QR Code
        </Link>
      </div>
    </div>
  );
}

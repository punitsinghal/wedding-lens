import Link from 'next/link';
import type { AssignedEvent } from '@/types/api';

interface Props {
  event: AssignedEvent;
}

export default function AssignedEventCard({ event }: Props) {
  const formattedDate = new Date(event.event_date ?? event.created_at).toLocaleDateString('en-IN', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  });

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-gray-900 truncate">{event.name}</h3>
          {(event.bride_name || event.groom_name) && (
            <p className="text-sm text-gray-500 mt-0.5">
              {event.bride_name} &amp; {event.groom_name}
            </p>
          )}
          <p className="text-xs text-gray-400 mt-1">{formattedDate}</p>
        </div>
        <span className="flex-shrink-0 text-xs font-medium text-gray-500 bg-gray-100 px-2 py-1 rounded-full">
          Photographer
        </span>
      </div>
      <div className="mt-4">
        <Link
          href={`/events/${event.id}/photos`}
          className="text-sm text-blue-600 hover:text-blue-800 font-medium"
        >
          Manage Photos &rarr;
        </Link>
      </div>
    </div>
  );
}

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
    <div className="card elev-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="card-title text-[21px] truncate">{event.name}</h3>
          {(event.bride_name || event.groom_name) && (
            <p className="text-sm opacity-70 truncate mt-0.5">
              {event.bride_name} &amp; {event.groom_name}
            </p>
          )}
          <p className="card-meta mt-1">{formattedDate}</p>
        </div>
        <span className="tag tag-accent-2 flex-shrink-0">Photographer</span>
      </div>
      <div className="pt-1">
        <Link href={`/events/${event.id}/photos`} className="btn btn-secondary text-sm">
          Manage Photos &rarr;
        </Link>
      </div>
    </div>
  );
}

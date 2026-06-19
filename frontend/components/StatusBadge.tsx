import type { EventStatus } from '@/types/api';

interface Props {
  status: EventStatus;
}

const statusStyles: Record<EventStatus, string> = {
  draft: 'bg-gray-100 text-gray-700',
  published: 'bg-green-100 text-green-700',
  suspended: 'bg-yellow-100 text-yellow-800',
  deleted: 'bg-red-100 text-red-700',
};

const statusLabels: Record<EventStatus, string> = {
  draft: 'Draft',
  published: 'Published',
  suspended: 'Suspended',
  deleted: 'Deleted',
};

export default function StatusBadge({ status }: Props) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusStyles[status]}`}
    >
      {statusLabels[status]}
    </span>
  );
}

import type { EventStatus } from '@/types/api';

interface Props {
  status: EventStatus;
}

const statusClasses: Record<EventStatus, string> = {
  draft: 'tag tag-neutral',
  published: 'tag tag-accent',
  suspended: 'tag tag-outline',
  deleted: 'tag tag-danger',
};

const statusLabels: Record<EventStatus, string> = {
  draft: 'Draft',
  published: 'Published',
  suspended: 'Suspended',
  deleted: 'Deleted',
};

export default function StatusBadge({ status }: Props) {
  return <span className={statusClasses[status]}>{statusLabels[status]}</span>;
}

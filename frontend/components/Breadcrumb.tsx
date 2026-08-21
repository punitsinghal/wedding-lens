import Link from 'next/link';
import type { ReactNode } from 'react';

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface Props {
  items: BreadcrumbItem[];
  trailing?: ReactNode;
}

// Shared breadcrumb used across owner and admin pages. The last item is
// treated as the current page (no link, full opacity/bold); earlier items
// are linked when they have an `href`. See docs/decisions for rationale.
export default function Breadcrumb({ items, trailing }: Props) {
  return (
    <nav aria-label="Breadcrumb" className="flex items-center gap-2 mb-6 text-sm flex-wrap opacity-80">
      {items.map((item, index) => {
        const isLast = index === items.length - 1;
        return (
          <span key={`${item.label}-${index}`} className="flex items-center gap-2">
            {index > 0 && <span className="opacity-50">/</span>}
            {item.href && !isLast ? (
              <Link href={item.href} className="hover:text-accent truncate">
                {item.label}
              </Link>
            ) : (
              <span className={`truncate ${isLast ? 'font-medium opacity-100' : ''}`}>
                {item.label}
              </span>
            )}
          </span>
        );
      })}
      {trailing}
    </nav>
  );
}

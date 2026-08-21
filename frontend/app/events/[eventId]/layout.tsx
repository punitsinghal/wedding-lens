'use client';

import { ReactNode } from 'react';
import { useParams, usePathname } from 'next/navigation';
import Link from 'next/link';

export default function EventLayout({ children }: { children: ReactNode }) {
  const params = useParams();
  const pathname = usePathname();
  const eventId = params.eventId as string;

  const overviewHref = `/events/${eventId}`;
  const LINKS = [
    { href: overviewHref, label: 'Overview' },
    { href: `/events/${eventId}/photos`, label: 'Manage Photos' },
    { href: `/events/${eventId}/albums`, label: 'Manage Albums' },
    { href: `/events/${eventId}/qr`, label: 'QR Code' },
  ];

  return (
    <div>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 pt-8 flex gap-2 flex-wrap">
        {LINKS.map((link) => {
          // Overview's href is a string-prefix of every other link's href, so
          // it needs an exact match; the other links use startsWith so their
          // active state still covers nested routes (e.g. album detail under
          // /albums).
          const isActive =
            link.href === overviewHref
              ? pathname === link.href
              : pathname?.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`btn text-xs px-3 py-1.5 ${isActive ? 'btn-primary' : 'btn-secondary'}`}
            >
              {link.label}
            </Link>
          );
        })}
      </div>
      {children}
    </div>
  );
}

'use client';

import { ReactNode } from 'react';
import { useParams, usePathname } from 'next/navigation';
import Link from 'next/link';

export default function EventLayout({ children }: { children: ReactNode }) {
  const params = useParams();
  const pathname = usePathname();
  const eventId = params.eventId as string;

  const LINKS = [
    { href: `/events/${eventId}/photos`, label: 'Manage Photos' },
    { href: `/events/${eventId}/albums`, label: 'Manage Albums' },
    { href: `/events/${eventId}/qr`, label: 'QR Code' },
  ];

  return (
    <div>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 pt-8 flex gap-2 flex-wrap">
        {LINKS.map((link) => {
          const isActive = pathname?.startsWith(link.href);
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

'use client';

import { useState, useEffect } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { getEventBySlug } from '@/lib/api';
import { isGuestAuthenticated } from '@/lib/auth';
import type { EventPublicOut } from '@/types/api';

export default function GuestGallery() {
  const router = useRouter();
  const params = useParams();
  const slug = params.slug as string;

  const [event, setEvent] = useState<EventPublicOut | null>(null);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    getEventBySlug(slug)
      .then((ev) => {
        if (!isGuestAuthenticated(ev.id)) {
          router.replace(`/g/${slug}`);
          return;
        }
        setEvent(ev);
      })
      .catch(() => {
        router.replace(`/g/${slug}`);
      })
      .finally(() => setIsChecking(false));
  }, [slug, router]);

  if (isChecking || !event) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-400 text-sm">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="max-w-sm w-full text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">{event.name}</h1>
        <p className="text-sm text-gray-500">Photos coming soon</p>
      </div>
    </div>
  );
}

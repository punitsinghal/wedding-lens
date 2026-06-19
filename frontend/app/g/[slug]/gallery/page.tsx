'use client';

import { useParams } from 'next/navigation';

export default function GuestGallery() {
  const params = useParams();
  const slug = params.slug as string;

  return (
    <div className="min-h-screen flex items-center justify-center">
      <p className="text-gray-600">
        Gallery for event <strong>{slug}</strong> coming soon.
      </p>
    </div>
  );
}

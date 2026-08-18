'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { isAuthenticated, isAdmin } from '@/lib/auth';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace('/login');
    } else if (!isAdmin()) {
      router.replace('/dashboard');
    }
  }, [router]);

  return (
    <>
      <div className="bg-neutral-900 text-bg px-4 sm:px-6 py-2.5 flex items-center gap-3">
        <span className="tag bg-accent-800 text-accent-200">Platform admin</span>
      </div>
      {children}
    </>
  );
}

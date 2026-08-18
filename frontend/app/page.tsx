'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { isAuthenticated } from '@/lib/auth';
import { IllustrationTile } from '@/components/HomeIllustrations';

export default function RootPage() {
  const router = useRouter();
  const [checkingAuth, setCheckingAuth] = useState(true);

  useEffect(() => {
    if (isAuthenticated()) {
      router.replace('/dashboard');
    } else {
      setCheckingAuth(false);
    }
  }, [router]);

  if (checkingAuth) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <p className="text-sm opacity-60">Redirecting...</p>
      </div>
    );
  }

  return <MarketingHome />;
}

function CalendarIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="2.5" y="4" width="15" height="13" rx="2" stroke="currentColor" strokeWidth="1.5" />
      <path d="M2.5 8h15M6 2.5v3M14 2.5v3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function ScanShareIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <rect x="3" y="2" width="8" height="13" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M13 6a4 4 0 010 5.5M15.5 3.5a8 8 0 010 10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function FaceSearchIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M12.5 12.5L17 17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="6.5" cy="8" r="0.6" fill="currentColor" />
      <circle cx="10.5" cy="8" r="0.6" fill="currentColor" />
      <path d="M6.8 10.3c.6.6 1.8.6 2.4 0" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
    </svg>
  );
}

function QrIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="17" y="3" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="3" y="17" width="8" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.6" />
      <rect x="17" y="17" width="3" height="3" fill="currentColor" />
      <rect x="22" y="17" width="3" height="3" fill="currentColor" />
      <rect x="17" y="22" width="3" height="3" fill="currentColor" />
      <rect x="22" y="22" width="3" height="3" fill="currentColor" />
    </svg>
  );
}

const HOW_IT_WORKS_STEPS = [
  {
    icon: CalendarIcon,
    tone: 'accent' as const,
    title: 'Create your event',
    body: 'Add your names and date, pick how guests get in — a link, a code, or open access.',
  },
  {
    icon: ScanShareIcon,
    tone: 'accent-2' as const,
    title: 'Guests scan & share',
    body: "A QR code on the table cards or invite. No app, no sign-up — they're uploading in one tap.",
  },
  {
    icon: FaceSearchIcon,
    tone: 'accent' as const,
    title: 'Everyone finds themselves',
    body: 'A selfie search surfaces every photo a guest appears in — no more scrolling through hundreds of shots.',
  },
];

const HOST_BENEFITS = [
  {
    title: 'Albums that sort themselves',
    body: 'Ceremony, sangeet, reception — photos land in the right album as they come in.',
  },
  {
    title: 'Download everything, in full resolution',
    body: 'One ZIP, no compression, no watermarks.',
  },
  {
    title: 'Private by default',
    body: 'Only people with your link or code ever see a single photo.',
  },
];

function MarketingHome() {
  return (
    <div>
      {/* Hero */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 pt-12 pb-16 sm:pt-16 sm:pb-24">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-center">
          <div>
            <span className="tag tag-accent mb-5">No app to download</span>
            <h1 className="text-4xl sm:text-5xl lg:text-6xl mb-5">
              Every guest&apos;s photos, in one gallery.
            </h1>
            <p className="text-base sm:text-lg opacity-75 mb-8 max-w-md">
              Guests scan a QR code and start uploading in seconds — no account, no app. You get
              one private gallery with everything, searchable by face.
            </p>
            <div className="flex flex-wrap gap-3 mb-12">
              <Link href="/register" className="btn btn-primary">
                Create your event
              </Link>
              <a href="#how-it-works" className="btn btn-secondary">
                See how it works
              </a>
            </div>
            <div className="grid grid-cols-3 gap-6 max-w-md">
              <div>
                <p className="text-2xl sm:text-3xl">200K+</p>
                <p className="text-xs opacity-60 mt-1">Events hosted</p>
              </div>
              <div>
                <p className="text-2xl sm:text-3xl">40M+</p>
                <p className="text-xs opacity-60 mt-1">Photos collected</p>
              </div>
              <div>
                <p className="text-2xl sm:text-3xl">4.9&#9733;</p>
                <p className="text-xs opacity-60 mt-1">Average rating</p>
              </div>
            </div>
          </div>

          <div className="relative mt-4 lg:mt-0">
            <div
              className="absolute -top-8 -right-8 w-64 h-64 rounded-full bg-accent-2-100 blur-2xl opacity-70 -z-10"
              aria-hidden="true"
            />
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-4">
                <IllustrationTile variant="mandap" className="h-36 sm:h-40 rounded-[26px]" />
                <IllustrationTile variant="sangeet" className="h-52 sm:h-56 rounded-[26px]" />
              </div>
              <div className="flex flex-col gap-4 pt-8">
                <IllustrationTile variant="reception" className="h-52 sm:h-56 rounded-[26px]" />
                <IllustrationTile variant="corporate" className="h-36 sm:h-40 rounded-[26px]" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <div className="text-center max-w-xl mx-auto mb-12">
          <span className="tag tag-accent-2 mb-4">How it works</span>
          <h2 className="text-3xl sm:text-4xl">Set up in minutes, live all night</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {HOW_IT_WORKS_STEPS.map((step) => {
            const Icon = step.icon;
            return (
              <div key={step.title} className="card elev-sm items-start p-6">
                <div
                  className={`w-12 h-12 rounded-full grid place-items-center mb-2 ${
                    step.tone === 'accent'
                      ? 'bg-accent-100 text-accent-700'
                      : 'bg-accent-2-100 text-accent-2-700'
                  }`}
                >
                  <Icon />
                </div>
                <h3 className="card-title">{step.title}</h3>
                <p className="card-body">{step.body}</p>
              </div>
            );
          })}
        </div>
      </section>

      {/* Built for hosts */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-center">
          <div className="grid grid-cols-2 gap-3 order-2 lg:order-1">
            <IllustrationTile variant="mehendi" className="h-32 rounded-[26px]" />
            <IllustrationTile variant="baraat" className="h-48 rounded-[26px] mt-6" />
            <IllustrationTile variant="photobooth" className="h-48 rounded-[26px]" />
            <IllustrationTile variant="fireworks" className="h-32 rounded-[26px]" />
            <IllustrationTile variant="conference" className="h-32 rounded-[26px]" />
            <IllustrationTile variant="garland" className="h-48 rounded-[26px] mt-6" />
          </div>
          <div className="order-1 lg:order-2">
            <span className="tag tag-accent mb-4">Built for hosts</span>
            <h2 className="text-3xl sm:text-4xl mb-6">
              Every angle of the day, organized automatically
            </h2>
            <ul className="space-y-6">
              {HOST_BENEFITS.map((benefit) => (
                <li key={benefit.title} className="flex gap-3">
                  <span className="mt-2 w-2 h-2 rounded-full bg-accent flex-none" aria-hidden="true" />
                  <div>
                    <p className="font-semibold">{benefit.title}</p>
                    <p className="text-sm opacity-70 mt-1">{benefit.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* CTA band */}
      <section className="bg-accent-900 text-white py-16 sm:py-20">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 text-center">
          <h2 className="text-3xl sm:text-4xl mb-4">Don&apos;t miss a single moment</h2>
          <p className="opacity-70 mb-8">
            Free to start. No credit card. Your gallery is live in under two minutes.
          </p>
          <Link href="/register" className="btn bg-white hover:bg-neutral-100">
            Create your event — it&apos;s free
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-divider">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm opacity-70">
          <p>&copy; 2026 PicsLeLo</p>
          <Link href="/privacy" className="hover:text-accent hover:opacity-100 transition-colors">
            Privacy
          </Link>
        </div>
      </footer>

      <div className="card elev-lg flex-row items-center gap-3 fixed bottom-4 left-4 sm:bottom-6 sm:left-6 w-56 z-50 bg-teal-600 text-white">
        <span className="text-white flex-none" aria-hidden="true">
          <QrIcon />
        </span>
        <div>
          <p className="text-sm font-semibold">Scan to upload</p>
          <p className="text-xs opacity-80">No app needed</p>
        </div>
      </div>
    </div>
  );
}

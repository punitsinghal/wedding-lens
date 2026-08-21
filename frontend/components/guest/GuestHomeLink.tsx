import Link from 'next/link';

interface Props {
  slug: string;
}

// Shared "back to gallery" control for guest routes. Gallery is the guest's
// home (there's no back-link to the PIN/landing page — re-entering a code is
// worse UX than just going to Gallery). Used on Search and Favourites.
export default function GuestHomeLink({ slug }: Props) {
  return (
    <Link
      href={`/g/${slug}/gallery`}
      className="inline-flex items-center gap-1.5 opacity-70 hover:opacity-100 hover:text-accent transition-colors"
    >
      <svg
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        className="h-5 w-5"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18"
        />
      </svg>
      <span className="text-sm">Gallery</span>
    </Link>
  );
}

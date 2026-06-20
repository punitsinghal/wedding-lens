'use client';

interface SearchErrorProps {
  code: string;
  onRetry: () => void;
}

function errorMessage(code: string): string {
  switch (code) {
    case 'no_face_detected':
      return 'We couldn\'t detect a face in your photo. Please upload a clear selfie showing your face.';
    case 'no_dominant_face':
      return 'Your selfie contains multiple faces. Please upload a photo that shows only your face.';
    case 'file_too_large':
      return 'Your photo is too large (max 20 MB). Please choose a smaller image.';
    default:
      return 'Something went wrong. Please try again.';
  }
}

export default function SearchError({ code, onRetry }: SearchErrorProps) {
  return (
    <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
      <svg
        className="h-10 w-10 text-red-400 mb-4"
        xmlns="http://www.w3.org/2000/svg"
        fill="none"
        viewBox="0 0 24 24"
        strokeWidth={1.5}
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z"
        />
      </svg>
      <p className="text-gray-800 font-medium max-w-xs">{errorMessage(code)}</p>
      <button
        onClick={onRetry}
        className="mt-6 px-5 py-2 text-sm font-medium bg-blue-600 text-white rounded-full hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 transition-colors"
      >
        Try again
      </button>
    </div>
  );
}

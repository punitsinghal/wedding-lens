'use client';

interface Props {
  suggestions: string[];
  onSelect: (slug: string) => void;
}

export default function SlugSuggestions({ suggestions, onSelect }: Props) {
  if (suggestions.length === 0) return null;

  return (
    <div className="mt-2">
      <p className="text-xs text-gray-500 mb-1">Suggested alternatives (click to use):</p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((slug) => (
          <button
            key={slug}
            type="button"
            onClick={() => onSelect(slug)}
            className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {slug}
          </button>
        ))}
      </div>
    </div>
  );
}

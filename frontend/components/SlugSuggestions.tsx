'use client';

interface Props {
  suggestions: string[];
  onSelect: (slug: string) => void;
}

export default function SlugSuggestions({ suggestions, onSelect }: Props) {
  if (suggestions.length === 0) return null;

  return (
    <div className="mt-2">
      <p className="text-xs opacity-60 mb-1">Suggested alternatives (click to use):</p>
      <div className="flex flex-wrap gap-2">
        {suggestions.map((slug) => (
          <button
            key={slug}
            type="button"
            onClick={() => onSelect(slug)}
            className="tag tag-accent"
          >
            {slug}
          </button>
        ))}
      </div>
    </div>
  );
}

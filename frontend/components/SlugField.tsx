'use client';

import { validateSlug } from '@/lib/slugUtils';
import SlugSuggestions from './SlugSuggestions';

interface Props {
  value: string;
  onChange: (value: string) => void;
  suggestions?: string[];
  onSelectSuggestion?: (slug: string) => void;
  disabled?: boolean;
}

export default function SlugField({
  value,
  onChange,
  suggestions = [],
  onSelectSuggestion,
  disabled = false,
}: Props) {
  const validationError = value ? validateSlug(value) : null;

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Event URL Slug
      </label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder="e.g. priya-rahul"
        maxLength={50}
        className={`w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-50 disabled:text-gray-500 ${
          validationError
            ? 'border-red-400 focus:ring-red-400'
            : 'border-gray-300'
        }`}
      />
      <div className="mt-1 flex justify-between text-xs">
        {validationError ? (
          <span className="text-red-600">{validationError}</span>
        ) : (
          <span className="text-gray-400">
            Lowercase letters, digits, and hyphens only. Max 50 chars.
          </span>
        )}
        <span className={`ml-2 ${value.length > 50 ? 'text-red-600' : 'text-gray-400'}`}>
          {value.length}/50
        </span>
      </div>
      {suggestions.length > 0 && onSelectSuggestion && (
        <SlugSuggestions suggestions={suggestions} onSelect={onSelectSuggestion} />
      )}
    </div>
  );
}

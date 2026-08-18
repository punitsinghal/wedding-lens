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
    <div className="field">
      <label>Event URL Slug</label>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder="e.g. priya-rahul"
        maxLength={50}
        className="input"
        style={validationError ? { borderColor: '#b3261e' } : undefined}
      />
      <div className="mt-1 flex justify-between text-xs">
        {validationError ? (
          <span style={{ color: '#b3261e' }}>{validationError}</span>
        ) : (
          <span className="opacity-60">
            Lowercase letters, digits, and hyphens only. Max 50 chars.
          </span>
        )}
        <span className="ml-2 opacity-60" style={value.length > 50 ? { color: '#b3261e', opacity: 1 } : undefined}>
          {value.length}/50
        </span>
      </div>
      {suggestions.length > 0 && onSelectSuggestion && (
        <SlugSuggestions suggestions={suggestions} onSelect={onSelectSuggestion} />
      )}
    </div>
  );
}

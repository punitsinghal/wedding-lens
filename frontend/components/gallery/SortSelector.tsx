'use client';

type SortValue = 'latest' | 'popular' | 'photographer-choice';

interface SortSelectorProps {
  value: SortValue;
  onChange: (v: string) => void;
}

const OPTIONS: { value: SortValue; label: string }[] = [
  { value: 'latest', label: 'Latest' },
  { value: 'popular', label: 'Popular' },
  { value: 'photographer-choice', label: 'Photographer Choice' },
];

export default function SortSelector({ value, onChange }: SortSelectorProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="input !min-h-0 py-1.5 w-auto cursor-pointer"
    >
      {OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}

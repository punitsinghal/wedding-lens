'use client';

import type { AlbumTab } from '@/types/api';

interface AlbumFilterBarProps {
  tabs: AlbumTab[];
  activeAlbum: string | null;
  onChange: (cat: string | null) => void;
}

export default function AlbumFilterBar({ tabs, activeAlbum, onChange }: AlbumFilterBarProps) {
  return (
    <div className="overflow-x-auto">
      <div className="flex gap-2 pb-1 min-w-max">
        {tabs.map((tab) => {
          const isActive = tab.ceremony_category === activeAlbum;
          return (
            <button
              key={tab.ceremony_category ?? 'all'}
              onClick={() => onChange(tab.ceremony_category)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium whitespace-nowrap transition-colors ${
                isActive
                  ? 'bg-accent text-bg'
                  : 'bg-surface opacity-80 border border-divider hover:opacity-100'
              }`}
            >
              {tab.label}
              <span
                className={`text-xs px-1.5 py-0.5 rounded-full ${
                  isActive ? 'bg-accent-700 text-accent-100' : 'bg-neutral-200 opacity-70'
                }`}
              >
                {tab.photo_count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

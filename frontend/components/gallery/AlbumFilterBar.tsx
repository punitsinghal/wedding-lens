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
                  ? 'bg-gray-900 text-white'
                  : 'bg-white text-gray-700 border border-gray-200 hover:bg-gray-100'
              }`}
            >
              {tab.label}
              <span
                className={`text-xs px-1.5 py-0.5 rounded-full ${
                  isActive ? 'bg-gray-700 text-gray-200' : 'bg-gray-100 text-gray-500'
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

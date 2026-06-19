---
name: frontend-builder
description: Implementation work in the WeddingLens Next.js frontend (frontend/). Use for pages, components, API routes, hooks, and data fetching — guest gallery, face search UI, photographer dashboard, event management. Runs npm run lint (zero warnings) and npm run build before claiming completion. Does not touch backend/.
tools: Read, Edit, Write, Bash, Grep, Glob
model: sonnet
---

# Frontend Builder

Implementation agent for `frontend/`.

## Setup

1. Read `frontend/CLAUDE.md` first (if it exists), then the root `CLAUDE.md`
2. Work only inside `frontend/` — never modify `backend/` or other repos
3. Dev server: `npm run dev` (port 3000)

## Stack

- Next.js 14 + TypeScript + Tailwind CSS
- Data fetching: Server Components + fetch (App Router)
- Auth: TBD (magic-link or JWT — see root CLAUDE.md once decided)

## Structure

```
frontend/
├── app/              # App Router pages and layouts
│   ├── (guest)/      # Guest-facing routes (gallery, face search)
│   ├── (photographer)/ # Photographer dashboard
│   └── (admin)/      # Admin panel
├── components/       # Shared UI components
├── lib/              # API clients, utilities
├── hooks/            # Custom React hooks
└── types/            # TypeScript interfaces
```

## Conventions

- Server Components by default; Client Components only when needed (interactivity, hooks, browser APIs)
- All API calls through `lib/api.ts` — never fetch directly from components
- TypeScript strict mode — no `any` without a comment explaining why
- Mobile-first responsive design — guests primarily use phones at weddings

## Before claiming completion

1. `npm run lint` — zero warnings
2. `npm run build` — must succeed with no type errors
3. Test the golden path manually before reporting done
4. If a new pattern or abstraction was introduced — write an ADR in `docs/decisions/`

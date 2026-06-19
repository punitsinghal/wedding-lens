// Slug auto-generation and validation utilities

/**
 * Auto-generate a slug from bride and groom names.
 * Format: {brideName}-{groomName}, lowercase, only a-z 0-9 hyphens, max 50 chars.
 */
export function generateSlug(brideName: string, groomName: string): string {
  const combined = `${brideName}-${groomName}`;
  return combined
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 50);
}

/**
 * Validate a slug:
 * - max 50 chars
 * - only lowercase letters, digits, hyphens
 * - no leading/trailing hyphens
 * Returns error message string or null if valid.
 */
export function validateSlug(slug: string): string | null {
  if (!slug) return 'Slug is required.';
  if (slug.length > 50) return 'Slug must be 50 characters or fewer.';
  if (/^-|-$/.test(slug)) return 'Slug cannot start or end with a hyphen.';
  if (!/^[a-z0-9-]+$/.test(slug))
    return 'Slug may only contain lowercase letters, digits, and hyphens.';
  return null;
}

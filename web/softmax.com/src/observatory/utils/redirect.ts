/**
 * Sanitize a redirect path to prevent open-redirect and XSS attacks.
 *
 * Only allows relative paths starting with `/`. Rejects absolute URLs and protocol-relative URLs (`//`).
 */
export function sanitizeRedirectPath(path: string | null | undefined): string {
  if (!path) return "/";

  if (!path.startsWith("/") || path.startsWith("//")) return "/";

  return path;
}

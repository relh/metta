export function buildEmbeddedDiagnoseUrl(
  baseUrl: string,
  runId?: string | null,
): string {
  const url = new URL(baseUrl);
  if (runId) {
    const trimmed = runId.trim();
    if (trimmed) {
      const basePath = url.pathname.replace(/\/$/, "");
      url.pathname = `${basePath}/${encodeURIComponent(trimmed)}`;
    }
  }
  return url.toString();
}

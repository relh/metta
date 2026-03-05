export function buildEmbeddedPantheonUrl(baseUrl: string): string {
  const url = new URL(baseUrl);
  url.searchParams.set("tab", "pantheon");
  return url.toString();
}

type BardoPathArgs = {
  nameFilter?: string | null;
};

export function buildEmbeddedBardoUrl(
  baseUrl: string,
  { nameFilter }: BardoPathArgs = {},
): string {
  const url = new URL(baseUrl);

  if (nameFilter) {
    const trimmed = nameFilter.trim();
    if (trimmed) {
      url.searchParams.set("q", trimmed);
    }
  }

  return url.toString();
}

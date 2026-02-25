export type ScoreSortDirection = "asc" | "desc";

export function compareMissingLast(
  a: number | undefined,
  b: number | undefined,
  direction: ScoreSortDirection = "desc",
): number {
  if (a === undefined && b === undefined) return 0;
  if (a === undefined) return 1;
  if (b === undefined) return -1;
  return direction === "asc" ? a - b : b - a;
}

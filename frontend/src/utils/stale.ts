/** True when an ISO UTC timestamp is missing or older than the given duration. */

export function isTimestampStale(iso: string | undefined, maxAgeMs: number): boolean {
  if (!iso) {
    return true;
  }
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) {
    return true;
  }
  return Date.now() - parsed > maxAgeMs;
}

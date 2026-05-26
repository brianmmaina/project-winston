/**
 * Returns true if the US equity/futures market is likely open
 * (Mon–Fri 09:30–16:00 ET). Approximates ET using DST detection.
 */
export function isMarketHours(): boolean {
  const now = new Date();
  const day = now.getDay();
  if (day === 0 || day === 6) return false;
  // Detect DST: ET is UTC-4 in summer, UTC-5 in winter.
  const jan = new Date(now.getFullYear(), 0, 1);
  const jul = new Date(now.getFullYear(), 6, 1);
  const stdOff = Math.max(jan.getTimezoneOffset(), jul.getTimezoneOffset());
  const isDst = now.getTimezoneOffset() < stdOff;
  const etOffsetMs = (isDst ? 4 : 5) * 3600 * 1000;
  const etMs = now.getTime() - etOffsetMs + now.getTimezoneOffset() * 60 * 1000;
  const et = new Date(etMs);
  const minutes = et.getHours() * 60 + et.getMinutes();
  return minutes >= 9 * 60 + 30 && minutes < 16 * 60;
}

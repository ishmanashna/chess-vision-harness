/** Same-origin logout redirect target — blocks open redirects. */

export function safeLogoutPath(next) {
  if (typeof next !== "string" || !next) return "/";
  if (!next.startsWith("/") || next.startsWith("//")) return "/";
  if (next.includes("\\") || next.includes("\0")) return "/";
  return next;
}

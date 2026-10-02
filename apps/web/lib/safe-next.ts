/** Only same-site relative paths survive; anything else becomes "/". Mirrors the API's check. */
export function safeNext(path: string | null | undefined): string {
  if (!path || !path.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) {
    return "/";
  }
  return path;
}

export const SIGNED_IN_HOME = "/app";

/** Where to go after signing in. Without a real destination that's the signed-in home, never
 * the public home page or the sign-in page itself, either of which would loop back here. */
export function signInDestination(next: string | null | undefined): string {
  const path = safeNext(next);
  const pathname = path.split(/[?#]/, 1)[0] ?? "/";
  if (pathname === "/" || pathname === "/signin" || pathname.startsWith("/auth/")) {
    return SIGNED_IN_HOME;
  }
  return path;
}

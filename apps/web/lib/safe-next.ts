/** Only same-site relative paths survive; anything else becomes "/". Mirrors the API's check. */
export function safeNext(path: string | null | undefined): string {
  if (!path || !path.startsWith("/") || path.startsWith("//") || path.startsWith("/\\")) {
    return "/";
  }
  return path;
}

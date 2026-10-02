// Which pages the service worker may keep for offline use (ADR-005, ADR-030). Only public
// subdivision and lot pages: the same for everyone, never holding anyone's data. Shared by
// the service worker and the pages, so both agree.

// First path segments that are never a subdivision. Must cover the API's reserved slugs
// (RESERVED_SLUGS in apps/api) plus the app's own top-level routes.
const NOT_SUBDIVISIONS = new Set([
  "app", "q", "api", "v1", "graphql", "internal", "serwist", "icons", "static", "admin",
  "auth", "login", "logout", "signin", "signup", "account", "settings", "about", "help",
  "terms", "privacy", "offline", "_next", "maplibre",
]); // prettier-ignore

const SLUG = "[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?";
const LOT_NUMBER = "[A-Za-z0-9-]{1,16}";
const PUBLIC_PAGE = new RegExp(`^/(${SLUG})(?:/lots/(${LOT_NUMBER}))?$`);

/** The subdivision slug and, for a lot page, the lot number; null for any other path. */
export function publicPage(pathname: string): { slug: string; lot: string | null } | null {
  const match = PUBLIC_PAGE.exec(pathname);
  const slug = match?.[1];
  if (!match || !slug || NOT_SUBDIVISIONS.has(slug)) return null;
  return { slug, lot: match[2] ?? null };
}

export function isPublicPage(pathname: string): boolean {
  return publicPage(pathname) !== null;
}

/** The subdivision page a lot page belongs to: "/juniper-bench/lots/7" -> "/juniper-bench". */
export function subdivisionOf(pathname: string): string | null {
  const page = publicPage(pathname);
  return page?.lot ? `/${page.slug}` : null;
}

/** The lot pages among cached URLs, for the offline page. */
export function isLotPage(pathname: string): boolean {
  return publicPage(pathname)?.lot != null;
}

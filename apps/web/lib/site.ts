/** The public address of the site, for absolute links in link previews. SITE_URL is
 * https://cornerpin.app in production. */
export function siteUrl(): URL {
  return new URL(process.env.SITE_URL ?? "http://localhost:3300");
}

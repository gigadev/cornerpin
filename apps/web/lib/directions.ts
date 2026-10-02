/** Driving directions to a point, as a Google Maps link. It opens the app on phones and the
 * website elsewhere, and needs no key (ADR-027). */
export function directionsUrl(lng: number, lat: number): string {
  const destination = `${lat.toFixed(6)},${lng.toFixed(6)}`;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}`;
}

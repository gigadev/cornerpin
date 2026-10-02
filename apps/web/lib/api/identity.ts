import "server-only";

// In production the API is a private Cloud Run service: only callers with a Google ID token
// for an allowed service account get through (ADR-032). The web server gets one for its own
// service account from the metadata server and adds it to every API call. Locally
// API_AUDIENCE is unset and nothing is added.

const METADATA_IDENTITY =
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity";
// ID tokens last an hour; fetch a new one well before that.
const REUSE_MS = 45 * 60 * 1000;

let cached: { audience: string; token: string; fetchedAt: number } | null = null;

export async function apiAuthHeaders(): Promise<Record<string, string>> {
  const audience = process.env.API_AUDIENCE;
  if (!audience) return {};
  if (!cached || cached.audience !== audience || Date.now() - cached.fetchedAt > REUSE_MS) {
    const response = await fetch(`${METADATA_IDENTITY}?audience=${encodeURIComponent(audience)}`, {
      headers: { "Metadata-Flavor": "Google" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error(`Could not get an ID token: ${response.status}`);
    cached = { audience, token: await response.text(), fetchedAt: Date.now() };
  }
  return { authorization: `Bearer ${cached.token}` };
}

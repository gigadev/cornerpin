import "server-only";
import createClient from "openapi-fetch";
import { cookies } from "next/headers";
import { cache } from "react";
import { apiBaseUrl } from "./proxy";
import type { components, paths } from "./schema";

export type Me = components["schemas"]["Me"];
export type Tenant = components["schemas"]["Tenant"];
export type AuthProviders = components["schemas"]["AuthProviders"];

/** API client for server components and route handlers; forwards the visitor's cookies. */
export async function serverApi() {
  const cookieHeader = (await cookies()).toString();
  return createClient<paths>({
    baseUrl: apiBaseUrl(),
    headers: cookieHeader ? { cookie: cookieHeader } : {},
    cache: "no-store",
  });
}

/** The signed-in user, or null. Cached per request so layouts and pages share one call. */
export const getMe = cache(async (): Promise<Me | null> => {
  const api = await serverApi();
  const { data, response } = await api.GET("/v1/me");
  if (response.status === 401) return null;
  if (!data) throw new Error(`GET /v1/me failed: ${response.status}`);
  return data;
});

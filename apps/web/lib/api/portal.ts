import "server-only";
import { notFound, redirect } from "next/navigation";
import { cache } from "react";
import { serverApi, type Tenant } from "./server";

/** The data, or the right page: sign-in when signed out, 404 for anything not found or not the
 * user's (including malformed ids). */
export async function loadOr404<T>(
  request: Promise<{ data?: T; response: Response }>,
  currentPath: string,
): Promise<T> {
  const { data, response } = await request;
  if (response.status === 401) redirect(`/signin?next=${encodeURIComponent(currentPath)}`);
  if (data === undefined) notFound();
  return data;
}

/** The tenant for a portal page, cached per request for layouts and breadcrumbs. */
export const getTenant = cache(async (tenantId: string): Promise<Tenant> => {
  const api = await serverApi();
  return loadOr404(
    api.GET("/v1/tenants/{tenant_id}", { params: { path: { tenant_id: tenantId } } }),
    `/app/${tenantId}`,
  );
});

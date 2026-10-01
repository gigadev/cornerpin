import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { serverApi } from "@/lib/api/server";

// A tenant the user is not a member of is a 404, the same as one that does not exist, so the
// portal does not confirm which tenants exist (P1-03).
export default async function TenantPortal({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const api = await serverApi();
  const { data: tenant, response } = await api.GET("/v1/tenants/{tenant_id}", {
    params: { path: { tenant_id: tenantId } },
  });
  if (response.status === 401) redirect(`/signin?next=/app/${encodeURIComponent(tenantId)}`);
  if (!tenant) notFound();

  return (
    <>
      <p className="text-sm text-muted">
        <Link href="/app" className="underline">
          Organizations
        </Link>
      </p>
      <h1 className="mt-2 text-2xl font-semibold tracking-tight">{tenant.name}</h1>
      <p className="mt-3 text-muted">
        Signed in as {tenant.role}. Subdivisions, phases and lots are managed here from P1-04.
      </p>
    </>
  );
}

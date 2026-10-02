import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { LotForm } from "@/components/portal/lot-form";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";

export default async function NewLotPage({
  params,
}: {
  params: Promise<{ tenantId: string; subdivisionId: string }>;
}) {
  const { tenantId, subdivisionId } = await params;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const subdivision = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}", {
      params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } },
    }),
    `/app/${tenantId}/subdivisions/${subdivisionId}/lots/new`,
  );

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
          { href: `/app/${tenantId}/subdivisions/${subdivisionId}`, label: subdivision.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">New lot</h1>
      <LotForm
        tenantId={tenantId}
        subdivisionId={subdivisionId}
        phases={subdivision.phases.map(({ id, name }) => ({ id, name }))}
      />
    </div>
  );
}

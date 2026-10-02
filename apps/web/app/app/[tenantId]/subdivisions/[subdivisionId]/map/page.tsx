import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { GeoJsonImport } from "@/components/portal/geojson-import";
import { LotMapEditor } from "@/components/portal/lot-map-editor";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";

export default async function SubdivisionMapPage({
  params,
}: {
  params: Promise<{ tenantId: string; subdivisionId: string }>;
}) {
  const { tenantId, subdivisionId } = await params;
  const here = `/app/${tenantId}/subdivisions/${subdivisionId}/map`;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const path = { params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } } };
  const [map, subdivision] = await Promise.all([
    loadOr404(api.GET("/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}/map", path), here),
    loadOr404(api.GET("/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}", path), here),
  ]);

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
          { href: `/app/${tenantId}/subdivisions/${subdivisionId}`, label: subdivision.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">Map: {subdivision.name}</h1>
      <LotMapEditor
        tenantId={tenantId}
        subdivisionId={subdivisionId}
        initial={map}
        satelliteKey={process.env.MAPTILER_KEY ?? null}
      />
      <Card>
        <CardHeader>
          <CardTitle>Import lot shapes</CardTitle>
        </CardHeader>
        <CardContent>
          <GeoJsonImport
            tenantId={tenantId}
            subdivisionId={subdivisionId}
            phases={subdivision.phases.map(({ id, name }) => ({ id, name }))}
          />
        </CardContent>
      </Card>
    </div>
  );
}

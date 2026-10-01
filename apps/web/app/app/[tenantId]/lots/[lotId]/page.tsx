import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { DeleteLotButton } from "@/components/portal/delete-button";
import { DocumentsCard } from "@/components/portal/documents-card";
import { LotForm } from "@/components/portal/lot-form";
import { LotHistory } from "@/components/portal/lot-history";
import { PhotosCard } from "@/components/portal/photos-card";
import { PublishedBadge, StatusBadge } from "@/components/portal/status-badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";
import { formatPrice } from "@/lib/format";

export default async function LotPage({
  params,
}: {
  params: Promise<{ tenantId: string; lotId: string }>;
}) {
  const { tenantId, lotId } = await params;
  const here = `/app/${tenantId}/lots/${lotId}`;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const lot = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/lots/{lot_id}", {
      params: { path: { tenant_id: tenantId, lot_id: lotId } },
    }),
    here,
  );
  const lotPath = { params: { path: { tenant_id: tenantId, lot_id: lotId } } };
  const [subdivision, photos, documents] = await Promise.all([
    loadOr404(
      api.GET("/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}", {
        params: { path: { tenant_id: tenantId, subdivision_id: lot.subdivision_id } },
      }),
      here,
    ),
    loadOr404(api.GET("/v1/tenants/{tenant_id}/lots/{lot_id}/photos", lotPath), here),
    loadOr404(api.GET("/v1/tenants/{tenant_id}/lots/{lot_id}/documents", lotPath), here),
  ]);

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
          { href: `/app/${tenantId}/subdivisions/${lot.subdivision_id}`, label: lot.subdivision_name },
        ]}
      />
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Lot {lot.number}</h1>
        <StatusBadge status={lot.status} />
        <PublishedBadge published={lot.published} />
        <span className="text-muted-foreground tabular-nums">{formatPrice(lot.price)}</span>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Photos</CardTitle>
        </CardHeader>
        <CardContent>
          <PhotosCard tenantId={tenantId} lotId={lotId} photos={photos} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Documents</CardTitle>
        </CardHeader>
        <CardContent>
          <DocumentsCard tenantId={tenantId} lotId={lotId} documents={documents} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>History</CardTitle>
        </CardHeader>
        <CardContent>
          <LotHistory lot={lot} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Keyed on updated_at so the form starts from the saved values after each save. */}
          <LotForm
            key={lot.updated_at}
            tenantId={tenantId}
            subdivisionId={lot.subdivision_id}
            phases={subdivision.phases.map(({ id, name }) => ({ id, name }))}
            lot={lot}
          />
        </CardContent>
      </Card>

      <DeleteLotButton
        tenantId={tenantId}
        lotId={lot.id}
        subdivisionId={lot.subdivision_id}
        number={lot.number}
      />
    </div>
  );
}

import Link from "next/link";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { DeleteSubdivisionButton } from "@/components/portal/delete-button";
import { PhasesCard } from "@/components/portal/phases-card";
import { PublishedBadge, StatusBadge } from "@/components/portal/status-badge";
import { SubdivisionForm } from "@/components/portal/subdivision-form";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";
import { formatAcres, formatPrice, listingLabel } from "@/lib/format";

export default async function SubdivisionPage({
  params,
}: {
  params: Promise<{ tenantId: string; subdivisionId: string }>;
}) {
  const { tenantId, subdivisionId } = await params;
  const here = `/app/${tenantId}/subdivisions/${subdivisionId}`;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const subdivision = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/subdivisions/{subdivision_id}", {
      params: { path: { tenant_id: tenantId, subdivision_id: subdivisionId } },
    }),
    here,
  );

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{subdivision.name}</h1>
        <PublishedBadge published={subdivision.published} />
      </div>

      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3">
          <CardTitle>Lots</CardTitle>
          {subdivision.phases.length > 0 ? (
            <Button asChild size="sm">
              <Link href={`${here}/lots/new`}>New lot</Link>
            </Button>
          ) : (
            <span className="text-sm text-muted-foreground">Add a phase first</span>
          )}
        </CardHeader>
        <CardContent>
          {subdivision.lots.length === 0 ? (
            <p className="text-sm text-muted-foreground">No lots yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Lot</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Price</TableHead>
                  <TableHead className="hidden sm:table-cell">Phase</TableHead>
                  <TableHead className="hidden md:table-cell">Listing</TableHead>
                  <TableHead className="hidden md:table-cell text-right">Acreage</TableHead>
                  <TableHead className="hidden sm:table-cell">Visibility</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {subdivision.lots.map((lot) => (
                  <TableRow key={lot.id}>
                    <TableCell>
                      <Link
                        href={`/app/${tenantId}/lots/${lot.id}`}
                        className="font-medium underline-offset-4 hover:underline"
                      >
                        Lot {lot.number}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={lot.status} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatPrice(lot.price)}</TableCell>
                    <TableCell className="hidden sm:table-cell">{lot.phase_name}</TableCell>
                    <TableCell className="hidden md:table-cell">
                      {listingLabel(lot.listing_type)}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-right tabular-nums">
                      {formatAcres(lot.acreage)}
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <PublishedBadge published={lot.published} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Phases</CardTitle>
        </CardHeader>
        <CardContent>
          <PhasesCard
            tenantId={tenantId}
            subdivisionId={subdivisionId}
            phases={subdivision.phases}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent>
          <SubdivisionForm tenantId={tenantId} subdivision={subdivision} />
        </CardContent>
      </Card>

      <DeleteSubdivisionButton
        tenantId={tenantId}
        subdivisionId={subdivisionId}
        name={subdivision.name}
      />
    </div>
  );
}

import Link from "next/link";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { PublishedBadge } from "@/components/portal/status-badge";
import { Button } from "@/components/ui/button";
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

// A tenant the user is not a member of is a 404, the same as one that does not exist, so the
// portal does not confirm which tenants exist (P1-03).
export default async function TenantPortal({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const options = { params: { path: { tenant_id: tenantId } } };
  const [subdivisions, holds, waiting] = await Promise.all([
    loadOr404(api.GET("/v1/tenants/{tenant_id}/subdivisions", options), `/app/${tenantId}`),
    loadOr404(api.GET("/v1/tenants/{tenant_id}/hold-requests", options), `/app/${tenantId}`),
    loadOr404(
      api.GET("/v1/tenants/{tenant_id}/leads", {
        params: { ...options.params, query: { needs_human: true } },
      }),
      `/app/${tenantId}`,
    ),
  ]);
  const pendingHolds = holds.filter((hold) => hold.status === "pending").length;

  return (
    <div className="grid gap-6">
      <Breadcrumbs items={[{ href: "/app", label: "Organizations" }]} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">{tenant.name}</h1>
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link href={`/app/${tenantId}/leads`}>
              Leads
              {waiting.needs_human > 0 ? ` (${waiting.needs_human} need a person)` : ""}
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={`/app/${tenantId}/integrations`}>Integrations</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href={`/app/${tenantId}/inquiries`}>
              Inquiries and holds
              {pendingHolds > 0 ? ` (${pendingHolds} pending)` : ""}
            </Link>
          </Button>
          {tenant.financing_demo ? (
            <Button asChild variant="outline">
              <Link href={`/app/${tenantId}/financing`}>Financing (demo)</Link>
            </Button>
          ) : null}
          <Button asChild>
            <Link href={`/app/${tenantId}/subdivisions/new`}>New subdivision</Link>
          </Button>
        </div>
      </div>

      {subdivisions.length === 0 ? (
        <p className="text-muted-foreground">
          No subdivisions yet. Create one to add its phases and lots.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Subdivision</TableHead>
              <TableHead className="text-right">Lots</TableHead>
              <TableHead className="text-right">Available</TableHead>
              <TableHead className="hidden sm:table-cell">Visibility</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {subdivisions.map((subdivision) => (
              <TableRow key={subdivision.id}>
                <TableCell>
                  <Link
                    href={`/app/${tenantId}/subdivisions/${subdivision.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {subdivision.name}
                  </Link>
                  <div className="text-xs text-muted-foreground">/{subdivision.slug}</div>
                </TableCell>
                <TableCell className="text-right tabular-nums">{subdivision.lot_count}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {subdivision.available_count}
                </TableCell>
                <TableCell className="hidden sm:table-cell">
                  <PublishedBadge published={subdivision.published} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

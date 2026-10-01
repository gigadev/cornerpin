import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { SubdivisionForm } from "@/components/portal/subdivision-form";
import { getTenant } from "@/lib/api/portal";

export default async function NewSubdivisionPage({
  params,
}: {
  params: Promise<{ tenantId: string }>;
}) {
  const { tenantId } = await params;
  const tenant = await getTenant(tenantId);

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">New subdivision</h1>
      <SubdivisionForm tenantId={tenantId} />
    </div>
  );
}

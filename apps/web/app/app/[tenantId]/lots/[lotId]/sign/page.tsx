import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { PrintButton } from "@/components/portal/print-button";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";
import { qrSvg, shortSignUrl, signUrl } from "@/lib/qr";

// A printable sign for one lot (P1-11, ADR-031). It shows only what doesn't change, the
// subdivision, the lot number and the code, because price and status do change and the code
// always opens the current page.
export default async function LotSignPage({
  params,
}: {
  params: Promise<{ tenantId: string; lotId: string }>;
}) {
  const { tenantId, lotId } = await params;
  const here = `/app/${tenantId}/lots/${lotId}/sign`;
  const path = { params: { path: { tenant_id: tenantId, lot_id: lotId } } };
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const lot = await loadOr404(api.GET("/v1/tenants/{tenant_id}/lots/{lot_id}", path), here);
  // Created the first time anyone opens this page, then the same forever.
  const { code } = await loadOr404(
    api.POST("/v1/tenants/{tenant_id}/lots/{lot_id}/qr-code", path),
    here,
  );
  const url = signUrl(code);
  const svg = await qrSvg(url.href);

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
          {
            href: `/app/${tenantId}/subdivisions/${lot.subdivision_id}`,
            label: lot.subdivision_name,
          },
          { href: `/app/${tenantId}/lots/${lotId}`, label: `Lot ${lot.number}` },
        ]}
      />
      <div className="flex flex-wrap items-center justify-between gap-3 print:hidden">
        <h1 className="text-2xl font-semibold tracking-tight">Sign for Lot {lot.number}</h1>
        <PrintButton />
      </div>
      <p className="max-w-prose text-sm text-muted-foreground print:hidden">
        The code always opens this lot&apos;s current page, even if the subdivision&apos;s web
        address changes. Print on letter paper; a laminated sheet or a print shop sign both work.
        {lot.published
          ? null
          : " This lot isn't published yet, so until you publish it, scanning the code says " +
            "it isn't listed."}
      </p>

      <article
        aria-label="Sign"
        className={
          "mx-auto grid w-full max-w-[7in] justify-items-center gap-4 rounded-lg border " +
          "border-border bg-white p-8 text-center text-black " +
          "print:max-w-none print:border-0 print:p-0"
        }
      >
        <p className="text-2xl font-semibold sm:text-3xl">{lot.subdivision_name}</p>
        <p className="text-5xl font-bold tracking-tight sm:text-7xl">Lot {lot.number}</p>
        <div
          role="img"
          aria-label={`QR code for ${url.href}`}
          data-qr-url={url.href}
          className="w-full max-w-[5in] [&>svg]:h-auto [&>svg]:w-full"
          // Generated here from our own URL; it contains only the code's squares.
          dangerouslySetInnerHTML={{ __html: svg }}
        />
        <p className="text-xl sm:text-2xl">Scan for price, photos, documents and directions</p>
        <p className="font-mono text-lg">{shortSignUrl(url)}</p>
        <p className="text-sm">Cornerpin</p>
      </article>
    </div>
  );
}

import Link from "next/link";
import { redirect } from "next/navigation";
import { getMe } from "@/lib/api/server";

export default async function PortalHome() {
  const me = await getMe();
  if (!me) redirect("/signin?next=/app");

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Your organizations</h1>
      {me.memberships.length === 0 ? (
        <p className="mt-3 text-muted-foreground">
          You don&apos;t manage any subdivisions. Saved lots and alerts will show up here once
          those features arrive.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-border rounded border border-border bg-card">
          {me.memberships.map((membership) => (
            <li key={membership.tenant_id}>
              <Link
                href={`/app/${membership.tenant_id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-muted"
              >
                <span className="font-medium">{membership.tenant_name}</span>
                <span className="text-sm text-muted-foreground">{membership.role}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

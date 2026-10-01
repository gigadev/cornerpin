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
        <p className="mt-3 text-muted">
          You don&apos;t manage any subdivisions. Saved lots and alerts will show up here once
          those features arrive.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-line rounded border border-line bg-white">
          {me.memberships.map((membership) => (
            <li key={membership.tenant_id}>
              <Link
                href={`/app/${membership.tenant_id}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-surface"
              >
                <span className="font-medium">{membership.tenant_name}</span>
                <span className="text-sm text-muted">{membership.role}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

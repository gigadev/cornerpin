import Link from "next/link";
import { redirect } from "next/navigation";
import { getMe } from "@/lib/api/server";

export default async function PortalHome() {
  const me = await getMe();
  if (!me) redirect("/signin?next=/app");
  // Sign-in lands here by default; a buyer who manages nothing belongs on their account page.
  if (me.memberships.length === 0) redirect("/account");

  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">Your organizations</h1>
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
    </>
  );
}

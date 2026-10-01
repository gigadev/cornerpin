import Link from "next/link";
import { Fragment } from "react";

export type Crumb = { href: string; label: string };

export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground">
      {items.map((item, index) => (
        <Fragment key={item.href}>
          {index > 0 ? <span className="px-1.5">/</span> : null}
          <Link href={item.href} className="underline-offset-4 hover:underline">
            {item.label}
          </Link>
        </Fragment>
      ))}
    </nav>
  );
}

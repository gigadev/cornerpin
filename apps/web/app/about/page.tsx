import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { SiteHeader } from "@/components/site-header";

// How cornerpin.app is built: where it runs, the services it uses, how it deploys and what it's
// written in (ADR-044). Public and static like /help. Keep it in step with infra/ and
// .github/workflows/ when either changes.

export const dynamic = "force-static";
export const metadata: Metadata = {
  title: "How Cornerpin is built",
  description:
    "Where cornerpin.app runs, the Google Cloud and outside services it uses, how it deploys and the languages it's written in.",
  alternates: { canonical: "/about" },
};

const FACTS = [
  ["Region", "us-west1, Oregon"],
  ["Database", "Neon, AWS us-west-2"],
  ["Hosting cost", "about $0–1 a month"],
] as const;

const PATH: readonly [string, ReactNode][] = [
  [
    "Browser or installed app",
    "Buyers browse lots and ask questions. Owners use the portal, which the service worker never caches.",
  ],
  [
    "Firebase Hosting",
    <>
      <code>cornerpin.app</code> and <code>www</code>, with Google-managed HTTPS certificates. It
      passes every request to the web service.
    </>,
  ],
  [
    "Cloud Run: web (Next.js)",
    <>
      Renders the pages and forwards <code>/v1/*</code> to the API.
    </>,
  ],
  [
    "Cloud Run: api (FastAPI)",
    "REST for writes, GraphQL for public reads, plus webhooks. Every change that needs an outside call is written to an outbox in the same transaction.",
  ],
];

const REACHES = [
  ["Neon Postgres + PostGIS", "Row-level security keeps tenants apart"],
  ["Cloud Storage", "Lot photos and documents"],
  ["Outbox → Cloud Tasks", "Background jobs: Claude, Resend, Slack, Salesforce, web push"],
] as const;

const GOOGLE_CLOUD: readonly [string, ReactNode][] = [
  [
    "Cloud Run services",
    <>
      <code>web</code> (Next.js) and <code>api</code> (FastAPI). Both scale to zero when idle.
    </>,
  ],
  [
    "Cloud Run jobs",
    <>
      <code>migrate</code> runs the database migrations on every deploy; <code>ops</code> runs
      one-off commands such as seeding the demo.
    </>,
  ],
  [
    "Firebase Hosting",
    "The custom domains and certificates, in front of the web service. Free at this traffic.",
  ],
  [
    "Cloud Tasks",
    "Wakes the API to process background jobs right after a change, and again when a delayed job is due, such as the assistant's follow-up 15 minutes after a question.",
  ],
  ["Cloud Scheduler", "An hourly outbox sweep as a safety net, and daily housekeeping."],
  [
    "Secret Manager",
    "Every secret: database URLs, API keys, Slack and Resend secrets, and the key that encrypts each tenant's integration credentials. A feature's secrets reach the services only when that feature is switched on.",
  ],
  ["Cloud Storage", "Photos and documents for each lot."],
  [
    "Artifact Registry",
    <>
      The Docker images for <code>api</code> and <code>web</code>.
    </>,
  ],
  [
    "IAM and Workload Identity",
    "GitHub Actions deploys without a stored Google key. Separate service accounts for the API, web, tasks and deploys.",
  ],
  ["Billing budget", "An alert at $5 a month."],
];

const OUTSIDE: readonly [string, string | null, ReactNode][] = [
  [
    "Neon",
    "free plan",
    "Postgres 17 with PostGIS for lot shapes and maps. The API connects as a role that can only see the signed-in tenant's rows.",
  ],
  [
    "Anthropic Claude",
    "Sonnet 5.5",
    "The outreach assistant. It states only prices and availability it read through its tools, and hands a buyer to a person when unsure.",
  ],
  [
    "Resend",
    null,
    <>
      Sends sign-in links, alerts and the assistant&apos;s emails, and receives buyers&apos; replies
      at <code>reply.cornerpin.app</code> through a signed webhook.
    </>,
  ],
  [
    "Slack",
    null,
    <>
      Each owner adds the app to their own workspace. New leads, hold requests and handoffs post
      to a channel; <code>/lot</code> answers with a lot&apos;s status and price.
    </>,
  ],
  [
    "Salesforce",
    null,
    "Each owner connects their own org. Leads, approved holds (as Opportunities) and lots (as Products) stay in step.",
  ],
  ["Cloudflare Turnstile", null, "The bot check on public forms. Sign-in is passwordless."],
  ["GoDaddy", null, "Domain registrar and DNS."],
  [
    "GitHub Actions",
    null,
    <>
      Checks every pull request and push to <code>main</code>, deploys once those checks pass on{" "}
      <code>main</code>, and runs the assistant&apos;s live evals on request.
    </>,
  ],
];

const DEPLOY = [
  ["Check", "CI must pass: lint, type checks, API tests, web tests and browser tests"],
  ["Build", "Docker images for the API and web, pushed to Artifact Registry"],
  ["Migrate", "The migrate job brings the database up to date"],
  ["Deploy API", "A new Cloud Run revision takes the traffic"],
  ["Deploy web", "The same, for the Next.js app"],
] as const;

const LANGUAGES = [
  [
    "Python",
    "API",
    "FastAPI, Pydantic, SQLAlchemy, Alembic and the Anthropic SDK. Tested with pytest, checked with Ruff and Pyright.",
  ],
  [
    "TypeScript",
    "web",
    "Next.js App Router and React, an installable app with a service worker. Types are generated from the API's schema. Tested with Vitest and Playwright.",
  ],
  [
    "SQL",
    "data",
    "Postgres and PostGIS, with row-level security policies and triggers that queue integration events.",
  ],
  ["HCL", "infrastructure", "Terraform for every Google Cloud resource on this page."],
  [
    "And",
    "supporting",
    "GraphQL for public reads, Bash for deploy and secrets scripts, YAML for GitHub Actions and the Slack app manifest, and Docker.",
  ],
] as const;

const TALLY = [
  ["291", "API tests"],
  ["119", "web unit tests"],
  ["76", "browser tests, phone and desktop"],
  ["13", "scripted conversations for the assistant"],
  ["44", "architecture decision records"],
] as const;

const PRACTICES = [
  "Every tenant table has row-level security, with a test proving one tenant can't read another's rows.",
  "Calls to Claude, email, Slack and Salesforce never run during a page load. They run in background jobs fed by the outbox, with retries.",
  "The assistant sends nothing without recorded consent, honours opt-outs first, respects quiet hours in the buyer's time zone, and logs every send.",
  "Its evals replay recorded conversations free on every CI run, and include a planted made-up price that the checks must catch.",
  "Secrets live in Secret Manager, never in the web bundle or the repository. Tenants' own credentials are encrypted per tenant.",
];

function Section({
  id,
  eyebrow,
  title,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={`${id}-heading`} className="grid gap-5">
      <div className="grid gap-1">
        <p className="text-xs font-medium tracking-wider text-primary uppercase">{eyebrow}</p>
        <h2 id={`${id}-heading`} className="text-2xl font-semibold tracking-tight">
          {title}
        </h2>
      </div>
      {children}
    </section>
  );
}

function Table({
  label,
  rows,
}: {
  label: string;
  rows: readonly (readonly [string, string | null, ReactNode])[];
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full text-sm">
        <thead className="bg-muted text-left text-xs tracking-wider text-muted-foreground uppercase">
          <tr>
            <th scope="col" className="px-4 py-2.5 font-medium">
              Service
            </th>
            <th scope="col" className="px-4 py-2.5 font-medium">
              {label}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([name, tag, text]) => (
            <tr key={name} className="border-t border-border align-top">
              <th scope="row" className="px-4 py-3 text-left font-semibold whitespace-nowrap">
                {name}
                {tag ? (
                  <span className="block text-xs font-normal text-muted-foreground">{tag}</span>
                ) : null}
              </th>
              <td className="px-4 py-3">{text}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AboutPage() {
  return (
    <>
      <SiteHeader />
      <main className="contours">
        <div className="mx-auto grid max-w-4xl gap-14 px-4 py-10">
          <div className="grid gap-4">
            <p className="text-xs font-medium tracking-wider text-primary uppercase">
              cornerpin.app · how it runs
            </p>
            <h1 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
              How Cornerpin is built
            </h1>
            <p className="max-w-prose text-lg text-muted-foreground">
              A multi-tenant app for selling subdivision lots, with an AI assistant that follows up
              with buyers and integrations with Slack and Salesforce. It runs on Google Cloud, with
              its database on Neon. Terraform defines every piece, and a merge to{" "}
              <code>main</code> deploys it.
            </p>
            <ul aria-label="At a glance" className="flex flex-wrap gap-2 text-sm">
              {FACTS.map(([label, value]) => (
                <li key={label} className="rounded-full border border-border bg-card px-3 py-1.5">
                  {label} <span className="font-medium text-primary">{value}</span>
                </li>
              ))}
            </ul>
          </div>

          <Section id="path" eyebrow="Request path" title="From a browser to the database">
            <ol className="grid">
              {PATH.map(([what, why]) => (
                <li key={what} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-3">
                  <span aria-hidden="true" className="grid grid-rows-[auto_1fr] justify-items-center">
                    <span className="mt-4 size-3 rotate-45 border-2 border-primary bg-background" />
                    <span className="mt-1 w-0.5 border-l-2 border-dashed border-primary" />
                  </span>
                  <div className="mb-3 grid gap-1 rounded-xl border border-border bg-card px-4 py-3">
                    <span className="font-semibold">{what}</span>
                    <span className="text-sm text-muted-foreground">{why}</span>
                  </div>
                </li>
              ))}
              <li className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-3">
                <span aria-hidden="true" className="grid justify-items-center">
                  <span className="mt-4 size-3 rotate-45 border-2 border-primary bg-background" />
                </span>
                <div className="grid gap-3 rounded-xl border border-border bg-card px-4 py-3">
                  <span className="font-semibold">What the API reaches</span>
                  <ul className="grid gap-2 sm:grid-cols-3">
                    {REACHES.map(([name, text]) => (
                      <li
                        key={name}
                        className="rounded-b-lg border-t-2 border-primary bg-accent px-3 py-2 text-sm"
                      >
                        <span className="block font-semibold">{name}</span>
                        {text}
                      </li>
                    ))}
                  </ul>
                </div>
              </li>
            </ol>
          </Section>

          <Section id="google-cloud" eyebrow="Google Cloud" title="The services it runs on">
            <Table
              label="What it does here"
              rows={GOOGLE_CLOUD.map(([name, text]) => [name, null, text] as const)}
            />
          </Section>

          <Section id="outside" eyebrow="Outside services" title="What it connects to">
            <Table label="Use" rows={OUTSIDE} />
          </Section>

          <Section id="deploy" eyebrow="Delivery" title="What a merge to main does">
            <ol className="grid gap-2 sm:grid-cols-5">
              {DEPLOY.map(([step, text], index) => (
                <li
                  key={step}
                  className="grid content-start gap-1 rounded-xl border border-border bg-card px-3 py-3 text-sm"
                >
                  <span className="text-xs font-medium tracking-wider text-primary uppercase">
                    Step {index + 1}
                  </span>
                  <span className="font-semibold">{step}</span>
                  <span className="text-muted-foreground">{text}</span>
                </li>
              ))}
            </ol>
          </Section>

          <Section id="languages" eyebrow="Languages" title="What it's written in">
            <dl className="grid gap-x-8 gap-y-5 sm:grid-cols-2">
              {LANGUAGES.map(([name, role, text]) => (
                <div key={name} className="grid content-start gap-1">
                  <dt className="font-semibold">
                    {name} <span className="text-xs font-normal text-muted-foreground">{role}</span>
                  </dt>
                  <dd className="text-sm text-muted-foreground">{text}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <Section id="practice" eyebrow="Engineering practice" title="How it's kept honest">
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-5">
              {TALLY.map(([count, what]) => (
                <div key={what} className="grid content-start gap-0.5 bg-card px-4 py-3">
                  <dt className="text-sm text-muted-foreground">{what}</dt>
                  <dd className="order-first text-2xl font-semibold text-primary tabular-nums">
                    {count}
                  </dd>
                </div>
              ))}
            </dl>
            <ul className="grid max-w-prose list-disc gap-2 pl-5 marker:text-primary">
              {PRACTICES.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </Section>

          <p className="text-muted-foreground">
            Built by Scott Shepherd, Gigadev Consulting. To see it from a buyer&apos;s side, read{" "}
            <Link href="/help" className="underline">
              how Cornerpin works
            </Link>{" "}
            or{" "}
            <Link href="/juniper-bench" className="underline">
              open the demo subdivision
            </Link>
            .
          </p>
        </div>
      </main>
    </>
  );
}

import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { IntegrationActions, SalesforceForm } from "@/components/portal/integration-actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";
import {
  installNotice,
  salesforceSummary,
  slackSummary,
  type Integration,
} from "@/lib/integrations";

// A tenant's integrations (P2-07, P2-08; ADR-040, ADR-041). Slack posts new leads, hold
// requests and handoffs to a channel and answers /lot; Salesforce keeps Leads, Opportunities
// and lot Products in step. Credentials never reach this page.

export const metadata: Metadata = { title: "Integrations · Cornerpin" };

function IntegrationCard({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={`${id}-heading`}>
      <Card>
        <CardHeader>
          <CardTitle id={`${id}-heading`}>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">{children}</CardContent>
      </Card>
    </section>
  );
}

export default async function Integrations({
  params,
  searchParams,
}: {
  params: Promise<{ tenantId: string }>;
  searchParams: Promise<{ slack?: string }>;
}) {
  const { tenantId } = await params;
  const { slack: returned } = await searchParams;
  const tenant = await getTenant(tenantId);
  const api = await serverApi();
  const integrations = await loadOr404(
    api.GET("/v1/tenants/{tenant_id}/integrations", {
      params: { path: { tenant_id: tenantId } },
    }),
    `/app/${tenantId}/integrations`,
  );
  const of = (provider: Integration["provider"]) =>
    integrations.find((integration) => integration.provider === provider);
  const slack = of("slack");
  const salesforce = of("salesforce");
  const notice = installNotice(returned);

  return (
    <div className="grid gap-6">
      <Breadcrumbs
        items={[
          { href: "/app", label: "Organizations" },
          { href: `/app/${tenantId}`, label: tenant.name },
        ]}
      />
      <h1 className="text-2xl font-semibold tracking-tight">Integrations</h1>
      {notice ? (
        <p role="status" className="text-muted-foreground">
          {notice}
        </p>
      ) : null}

      {slack ? (
        <IntegrationCard
          id="slack"
          title="Slack"
          description={
            <>
              Posts new leads, hold requests and leads that need a person to a channel, and
              answers <code>/lot &lt;subdivision&gt; &lt;lot number&gt;</code> with the current
              status and price.
            </>
          }
        >
          <p>{slackSummary(slack)}</p>
          {slack.status === "connected" || slack.status === "failed" ? (
            <IntegrationActions
              tenantId={tenantId}
              provider="slack"
              enabled={slack.enabled}
              canToggle={slack.status === "connected"}
            />
          ) : null}
          {slack.available && slack.status !== "connected" ? (
            <div>
              <Button asChild>
                {/* A full navigation: the API sends the owner on to Slack. */}
                <a href={`/v1/tenants/${tenantId}/integrations/slack/install`}>
                  {slack.status === "failed" ? "Add Slack again" : "Add to Slack"}
                </a>
              </Button>
            </div>
          ) : null}
        </IntegrationCard>
      ) : null}

      {salesforce ? (
        <IntegrationCard
          id="salesforce"
          title="Salesforce"
          description="Each lead becomes a Salesforce Lead and follows its stage; an approved hold opens an Opportunity; each lot is a Product with its status and price."
        >
          <p>{salesforceSummary(salesforce)}</p>
          {salesforce.status !== "not_connected" ? (
            <IntegrationActions
              tenantId={tenantId}
              provider="salesforce"
              enabled={salesforce.enabled}
              canToggle={salesforce.status === "connected"}
            />
          ) : null}
          {salesforce.status === "not_connected" || salesforce.status === "failed" ? (
            <SalesforceForm tenantId={tenantId} />
          ) : null}
        </IntegrationCard>
      ) : null}
    </div>
  );
}

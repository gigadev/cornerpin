import type { Metadata } from "next";
import { Breadcrumbs } from "@/components/portal/breadcrumbs";
import { SlackActions } from "@/components/portal/slack-actions";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getTenant, loadOr404 } from "@/lib/api/portal";
import { serverApi } from "@/lib/api/server";
import { installNotice, slackSummary } from "@/lib/integrations";

// A tenant's integrations (P2-07, ADR-040). Slack posts new leads, hold requests and handoffs
// to a channel and answers /lot. Credentials never reach this page.

export const metadata: Metadata = { title: "Integrations · Cornerpin" };

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
  const slack = integrations.find((integration) => integration.provider === "slack");
  const notice = installNotice(returned);
  const canAdd = slack?.available && slack.status !== "connected";

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
        <section aria-labelledby="slack-heading">
          <Card>
          <CardHeader>
            <CardTitle id="slack-heading">Slack</CardTitle>
            <CardDescription>
              Posts new leads, hold requests and leads that need a person to a channel, and
              answers <code>/lot &lt;subdivision&gt; &lt;lot number&gt;</code> with the current
              status and price.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3">
            <p>{slackSummary(slack)}</p>
            {slack.status === "connected" || slack.status === "failed" ? (
              <SlackActions tenantId={tenantId} enabled={slack.enabled} />
            ) : null}
            {canAdd ? (
              <div>
                <Button asChild>
                  {/* A full navigation: the API sends the owner on to Slack. */}
                  <a href={`/v1/tenants/${tenantId}/integrations/slack/install`}>
                    {slack.status === "failed" ? "Add Slack again" : "Add to Slack"}
                  </a>
                </Button>
              </div>
            ) : null}
          </CardContent>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

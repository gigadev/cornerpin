import { expect, test } from "@playwright/test";
import { API_URL, DEMO_TENANT_ID } from "./fixtures";

// P2-07: the Integrations page. The e2e API has no Slack app, so Slack can't be added from
// here; the connection is made the local way, with a webhook nobody listens on, then switched
// off and removed from the page. The demo tenant has one Slack connection, so this runs on
// one viewport only.

test("an owner sees Slack's connection, switches its alerts off and disconnects it", async ({
  page,
  request,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop-portal", "one connection per tenant");

  await page.goto(`/app/${DEMO_TENANT_ID}`);
  await page.getByRole("link", { name: "Integrations" }).click();
  const slack = page.getByRole("region", { name: "Slack" });
  await expect(slack).toContainText("Slack isn't set up on this Cornerpin yet.");
  await expect(slack.getByRole("link", { name: "Add to Slack" })).toHaveCount(0);

  const connected = await request.post(`${API_URL}/v1/dev/integrations/slack`, {
    data: {
      tenant_id: DEMO_TENANT_ID,
      webhook_url: "http://127.0.0.1:9/e2e-slack",
      team_name: "E2E workspace",
      channel: "#lots",
    },
  });
  expect(connected.status()).toBe(204);
  await page.reload();
  await expect(slack).toContainText("Connected. Alerts on: #lots in E2E workspace");

  await slack.getByRole("button", { name: "Turn alerts off" }).click();
  await expect(slack).toContainText("Alerts off (/lot still answers): #lots in E2E workspace");
  await slack.getByRole("button", { name: "Disconnect" }).click();
  await expect(slack).toContainText("Slack isn't set up on this Cornerpin yet.");
});

// P2-08: Salesforce takes an org's credentials, and only for a Salesforce My Domain, so a
// mistyped address never receives the secret. (Connecting for real needs an org: P2-10.)
test("Salesforce asks for an org's My Domain and refuses any other address", async ({ page }) => {
  await page.goto(`/app/${DEMO_TENANT_ID}/integrations`);
  const salesforce = page.getByRole("region", { name: "Salesforce" });
  await expect(salesforce).toContainText("Not connected.");
  const form = salesforce.getByRole("form", { name: "Connect Salesforce" });
  await form.getByLabel("My Domain").fill("login.example.com");
  await form.getByLabel("Consumer key").fill("3MVG9-not-a-real-key");
  await form.getByLabel("Consumer secret").fill("not-a-real-secret");
  await form.getByRole("button", { name: "Connect Salesforce" }).click();
  await expect(form.getByRole("alert")).toContainText("Enter your org's My Domain");
  await expect(salesforce).toContainText("Not connected.");
});

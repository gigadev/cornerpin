import type { APIRequestContext, TestInfo } from "@playwright/test";

// Seeded by apps/api/src/cornerpin/e2e_server.py; keep in sync.
export const DEMO_TENANT_ID = "957ccd5e-b6d1-531f-a102-ddef309c396e";
export const OTHER_TENANT_ID = "1aca3c52-936f-5fd9-8a5b-aa1b6e00ae2e";
// The API the e2e run starts (playwright.config.ts).
export const API_URL = "http://localhost:8100";

/** An owner of the demo tenant, one per project so parallel runs never share an inbox. */
export function projectOwner(testInfo: TestInfo): string {
  return `owner+${testInfo.project.name}@demo.cornerpin.test`;
}

const MAILPIT = "http://localhost:8025/api/v1";

type MessageSummary = { ID: string };
type SearchResult = { messages: MessageSummary[] };
type Message = { Text: string };

export async function clearInbox(request: APIRequestContext, address: string): Promise<void> {
  await request.delete(`${MAILPIT}/search`, { params: { query: `to:"${address}"` } });
}

/** The sign-in link from the newest email to `address`, waiting for the outbox to send it. */
export async function signInLink(request: APIRequestContext, address: string): Promise<string> {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    const search = await request.get(`${MAILPIT}/search`, {
      params: { query: `to:"${address}"`, limit: "1" },
    });
    const { messages } = (await search.json()) as SearchResult;
    const newest = messages[0];
    if (newest) {
      const message = (await (await request.get(`${MAILPIT}/message/${newest.ID}`)).json()) as Message;
      const link = /https?:\/\/\S+\/auth\/verify\?token=\S+/.exec(message.Text)?.[0];
      if (link) return link;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`no sign-in email for ${address}`);
}

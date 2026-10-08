# Connecting Slack and Salesforce

How an owner connects each integration from **Integrations** in the owner portal, and what has
to exist first. Both are free. The design is in ADR-040 (Slack, and how credentials are kept)
and ADR-041 (Salesforce).

## Salesforce

Works locally as well as on cornerpin.app: Cornerpin calls Salesforce, and Salesforce never
calls back.

1. **An org.** A free Developer Edition org from
   [developer.salesforce.com/signup](https://developer.salesforce.com/signup) is enough. The
   username has to look like an email address but needn't be a real one. You sign in as an admin.
2. **An External Client App** in that org. Salesforce's screens change between releases, so the
   labels may differ a little:
   1. Setup (the gear) → search for **External Client App Manager** → **New External Client
      App**.
   2. Name it `Cornerpin`, give your email, and leave distribution **Local**.
   3. Under **API (Enable OAuth Settings)**, switch OAuth on:
      - **Callback URL:** required but unused; `https://cornerpin.app` will do.
      - **Scope:** add **Manage user data via APIs (api)**.
      - **Flow:** tick **Enable Client Credentials Flow**.

      Create the app.
   4. On the app's **Policies** tab, choose **Edit**, find the **Client Credentials Flow** and
      set **Run As** to your own (admin) user. Save.
   5. On the **Settings** tab, open the consumer details. Salesforce may email you a code first.
      Copy the **Consumer Key** and **Consumer Secret**.
   6. Setup → **My Domain** shows the org's address, like
      `something.develop.my.salesforce.com`.
3. **In Cornerpin**, open Integrations → Salesforce, enter the My Domain, consumer key and
   consumer secret, and choose **Connect Salesforce**.

   The page says "Connecting" while the worker signs in. It then creates Cornerpin's fields and
   permission set in the org (ADR-041) and sends every lot across as a Product. Refresh after a
   few seconds.

A new app can take a few minutes before Salesforce accepts its sign-ins. If the page shows that
Salesforce didn't accept the sign-in, wait, then enter the details again.

**What you'll see in Salesforce:**
- **Leads**, from Cornerpin's buyers; their status follows the lead's stage.
- **Opportunities** named "Hold: Lot …" for approved holds.
- **Products** for each lot, with **Lot status** and **Lot price**.

Each record carries a **Cornerpin ID**; don't edit it.

**Seeing Cornerpin's fields.** Cornerpin creates its fields and lets your user read them, but
Salesforce doesn't add new fields to existing screens. The quickest place to see them is a list
view:
1. App Launcher → **Products** → a list view such as **All Products**.
2. The gear by the list → **Select Fields to Display**.
3. Add **Lot status**, **Lot price** and **Cornerpin ID**, and save.

To show them on a Product's own page too:
1. Setup → **Object Manager** → **Product** → **Page Layouts** → **Product Layout**.
2. Drag the three fields into the Product Detail section and choose **Save**.
3. If the record page was customized in the **Lightning App Builder**, its Details tab must use
   the **Record Detail** component (which follows the layout). Save and **Activate** it as the
   org default.

On the production check (October 2026) the list view showed the fields at once, while the
record page still hadn't shown them after both steps. The data is the same either way; Leads
work the same way, under Object Manager → **Lead**.

## Slack

Slack only finishes an install over HTTPS, so **Add to Slack** works on cornerpin.app, not
locally.

1. **A workspace**, and Cornerpin's Slack app: at [api.slack.com/apps](https://api.slack.com/apps)
   choose **Create New App → From a manifest**, pick the workspace and paste
   [`infra/slack-app-manifest.yml`](../infra/slack-app-manifest.yml).
2. **The app's settings** go to the API, not to owners. Its **Client ID**, **Client Secret** and
   **Signing Secret** (Basic Information) become `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` and
   `SLACK_SIGNING_SECRET`, with an `INTEGRATIONS_KEY`. That's Secret Manager on cornerpin.app
   (P2-10).
3. **Owners** then choose **Add to Slack** on Integrations and pick a channel.

Locally, a tenant can be connected to an incoming webhook made by hand; see TEST_ACCOUNTS.md.

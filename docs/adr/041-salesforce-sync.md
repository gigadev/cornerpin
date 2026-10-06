# ADR-041: Salesforce sync: client credentials, upserts on Cornerpin IDs, fields made on connect

- **Status:** Accepted
- **Date:** 2026-10-06
- **Applies from:** P2-08

## Context

The plan asks for these to sync to Salesforce:
- a lead becomes a Salesforce Lead;
- stage changes set its status;
- an approved hold opens an Opportunity;
- lot status and price sync.

All of it should work on Developer Edition, with server-to-server auth, retried from the outbox
and idempotent through external IDs. Each tenant has its own org, so credentials are per tenant
(ADR-040). Salesforce has no Cornerpin ID fields, and no field for a lot's status.

## Decision

- **Auth: the OAuth 2.0 client credentials flow.**
  1. The owner makes an External Client App in their org, with the flow switched on and a run-as
     user.
  2. They type its consumer key and secret, and their org's My Domain, into the Integrations page.
  3. The key and secret are stored encrypted (ADR-040). The owner can write them but never read
     them back.
  4. A token is reused for half an hour, and fetched again if Salesforce says it has expired.
- **Credentials only ever go to a Salesforce My Domain.** The domain must be a
  `*.my.salesforce.com` host, checked by the API and again by the client, so a mistyped or
  malicious address never receives the secret.
- **Cornerpin sets the org up when it connects.** In the worker, it signs in and then, where
  missing:
  - creates a `Cornerpin_Id__c` external-ID field (unique) on Lead, Opportunity and Product2;
  - creates `Cornerpin_Status__c` and `Cornerpin_Price__c` on Product2;
  - creates a "Cornerpin integration" permission set that can read and write those fields, and
    assigns it to the run-as user.

  It uses the Tooling and REST APIs, so nobody clicks through Setup. It then sends every lot
  across, and only then is the connection connected. A refusal (bad credentials, or a run-as
  user without admin rights) leaves the connection failed, with Salesforce's reason shown to the
  owner.
- **Every write is an upsert on a Cornerpin ID**, so a retry after a lost answer updates the
  record the first try made.
  - **Lead:** keyed on the lead's id. Written on every inquiry, hold request, approved hold,
    handoff and stage change, from the lead's state at delivery time, so out-of-order deliveries
    still converge. The stage maps to a standard Lead Status:
    - new is "Open - Not Contacted";
    - contacted, engaged, holding and won are "Working - Contacted", because a converted status
      can't be set through the API;
    - lost is "Closed - Not Converted".

    Company is "Individual", and LeadSource is "Web".
  - **Opportunity:** keyed on the hold request's id, when a hold is approved. It's "Hold: Lot …
    (buyer)" at Negotiation/Review, the lot's price as Amount, closing 30 days after the
    decision.
  - **Product2:** keyed on the lot's id, for every lot, published or not (IsActive says which),
    with its status and price. Sent in batches of 200 when the org is connected, then one at a
    time when a lot is added or its number, status, price, listing type or publication changes,
    queued by a trigger only for tenants with Salesforce connected and syncing.
- **Errors split in two.**
  - **Refusals** (400, 401 after signing in again, 403, 404, or a record a batch rejected) mark
    the connection failed with the reason, and aren't retried.
  - **Outages** (5xx, timeouts) are retried by the outbox.
- **Duplicate rules don't block Cornerpin.** Writes send `Sforce-Duplicate-Rule-Header:
  allowSave=true`, so a lead with a familiar email address isn't held back.
- **API version v62.0**, pinned in one constant.

## Alternatives considered

- **Asking owners to create the fields themselves, or to deploy a metadata package with the
  Salesforce CLI:** too many steps for an owner. A managed package is the long-term answer for
  orgs that won't grant admin rights to the run-as user.
- **The JWT bearer flow:** it needs a certificate per org; client credentials needs only the
  app's key and secret.
- **Lots as a custom object:** Product2 is standard, and is what an Opportunity's line items
  would use later.

## Consequences

- The run-as user needs rights to change metadata the first time (an admin on Developer
  Edition). After that, the permission set is all it needs.
- Owners whose org uses other Lead Status or Opportunity stage values get a refusal until the
  mapping can be set per tenant. That isn't built.
- Leads and lots created before connecting: lots are sent when connecting, but leads appear when
  they next change.
- Deleting a lot in Cornerpin doesn't delete its Product, and a lead won or lost doesn't close
  its Opportunity. Both are worth adding with a real tenant's process in mind.

## Related

ADR-010 (outbox), ADR-012 (integrations), ADR-035 (leads), ADR-040 (credentials and Slack)

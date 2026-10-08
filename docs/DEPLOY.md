# Deploying Cornerpin

How production is set up and how to change it. The decisions are in
[ADR-032](adr/032-production-deployment.md); the infrastructure is Terraform in [`infra/`](../infra).
Expected cost: about $0–2 a month on Google Cloud, with a $5 budget alert. Phase 2 adds about
$0.36 a month there (Secret Manager versions past the free six), plus the Claude API on
Anthropic's own bill, about $2–5 a month at demo volume, capped by a limit set in Anthropic's
Console. Resend's receiving, Slack and Salesforce Developer Edition are free.

Steps marked **Scott** need your accounts or a browser sign-in. The rest Claude Code can run
once you've done those, with your go-ahead before anything is created.

## 1. Accounts (once)

1. **Scott — Google Cloud.** Create a project (for example `cornerpin-prod`) and link it to a
   billing account. Note the project ID and billing account ID
   (Billing → Account management).
2. **Scott — Neon.** Create a project named `cornerpin`, region AWS US West 2 (Oregon),
   Postgres 17. In the branch's compute settings, set the maximum size to 0.25 CU so the free
   plan's 100 CU-hours a month go a long way.
3. **Scott — Resend.** Add the domain `cornerpin.app` and the DNS records it shows, then create
   an API key. Sending access is enough for Phase 1; Phase 2 reads buyers' replies, which needs
   **Full access** (a sending-only key gets a 401 on received mail). Sign-in emails come from `hello@cornerpin.app` unless you
   choose another sender (`email_from` in `terraform.tfvars`).
4. **Scott — Cloudflare Turnstile.** Add a widget for `cornerpin.app` (Managed mode). Keep the
   site key (public) and the secret key.
5. **Scott — tell Claude:** the project ID, the billing account ID, the Turnstile site key, the
   email that should own the demo tenant, Ricky's tenant name and email, and where
   `cornerpin.app` is registered (for the DNS step).

## 2. Infrastructure

1. **Scott:** sign in on this machine (opens a browser):

   ```bash
   gcloud auth login
   ```

   ```bash
   gcloud auth application-default login
   ```

2. Create the Terraform state bucket and initialise:

   ```bash
   infra/scripts/bootstrap.sh cornerpin-prod
   ```

   ```bash
   cd infra && terraform init -backend-config="bucket=cornerpin-prod-tfstate"
   ```

3. Copy `infra/terraform.tfvars.example` to `infra/terraform.tfvars` and fill it in. Cloud Run
   won't start a service whose secrets are empty, so create the secret containers first:

   ```bash
   terraform apply -target=google_secret_manager_secret.app
   ```

4. **Scott:** put the secrets in (prompts; nothing is echoed or saved):

   ```bash
   infra/scripts/set-secrets.sh cornerpin-prod
   ```

5. Review the full plan, then apply it:

   ```bash
   terraform plan -out=tfplan
   ```

   ```bash
   terraform apply tfplan
   ```

   If the apply stops at Firebase, open https://console.firebase.google.com, add Firebase to
   the existing project (this accepts Firebase's terms), and apply again.

6. Set the repository variables the deploy workflow reads, from
   `terraform output github_variables`, plus `SMOKE_URL` set to `terraform output hosting_url`
   until DNS is done.

## 3. DNS

**Scott:** at the registrar, add the records from `terraform output dns_records` (apex and
`www`). Firebase issues the certificate once they resolve; that can take from minutes to a day.
Then delete the `SMOKE_URL` repository variable.

## 4. First deploy

1. Run the **Deploy** workflow by hand (Actions → Deploy → Run workflow). It builds both images,
   runs migrations, deploys, and smoke-checks the site. The first run's smoke check fails at
   `/juniper-bench` because there's no demo yet.
2. Seed the demo subdivision, owned by your address:

   ```bash
   gcloud run jobs execute ops --region us-west1 --wait --args="-m,cornerpin.ops,seed-demo,--owner-email,you@example.com"
   ```

3. Create Ricky's tenant. He signs in with an emailed link to that address:

   ```bash
   gcloud run jobs execute ops --region us-west1 --wait --args="-m,cornerpin.ops,create-tenant,--name,Ricky's Land Co.,--owner-email,ricky@example.com,--owner-name,Ricky"
   ```

4. Run the Deploy workflow again; the smoke check passes.

## 5. Phase 2: the assistant, replies, Slack and Salesforce

The decisions are in [ADR-042](adr/042-phase-2-in-production.md). **Order matters:** the
Phase 2 code won't start without `INTEGRATIONS_KEY`, so its secrets go in, and Terraform
applies, *before* the Phase 2 branch merges. Each feature has a switch in `terraform.tfvars`.
Leave a switch off, and that feature stays dormant, until its secret is in.

1. **Scott:** sign in again; the earlier sign-in has expired.

   ```bash
   gcloud auth login
   ```

   ```bash
   gcloud auth application-default login
   ```

2. Create the new secret containers:

   ```bash
   cd infra && terraform apply -target=google_secret_manager_secret.app
   ```

3. **Scott, in your accounts.** Each is optional except the first; skip any you're not ready
   for.
   - **Anthropic:** at platform.claude.com, create a key for production (separate from your
     local one), and check the monthly spend limit (about $10).
   - **Resend, for replies:**
     1. On Domains, enable receiving for `reply.cornerpin.app` (a subdomain, so mail to
        `cornerpin.app` itself is untouched) and copy the MX record it shows.
     2. At GoDaddy, add that MX record with host `reply`.
     3. Back in Resend, choose **I've added the record** and wait until it's verified.
        Resend drops mail for a domain whose receiving record isn't verified.
     4. On Webhooks, add `https://cornerpin.app/v1/webhooks/resend` for the `email.received`
        event, and keep its signing secret (`whsec_...`).
     5. Check the API key is **Full access**. The webhook only says a reply arrived; the API
        then fetches it with the key, and a sending-only key gets a 401. If it's
        sending-only, create a Full access key and enter it at the script's Resend API key
        prompt in step 4.
   - **Slack:**
     1. At api.slack.com/apps, choose **Create New App → From a manifest**, and paste
        [`infra/slack-app-manifest.yml`](../infra/slack-app-manifest.yml).
     2. Keep the Client ID, Client Secret and Signing Secret from **Basic Information**.
     3. To let owners outside your own workspace add it, switch on **Manage Distribution →
        Public Distribution**. Slack charges nothing, and there's no review unless it's listed
        in the Slack Marketplace.
   - **Salesforce:** nothing here; it's connected from the portal in step 7.

4. **Scott:** put the secrets in. Enter skips any of them. `integrations-key` is generated, and
   only once: making a new one would disconnect every tenant's integrations.

   ```bash
   infra/scripts/set-secrets.sh cornerpin-515026 phase2
   ```

5. Switch on what you set, in `infra/terraform.tfvars`:

   ```hcl
   agent_enabled        = true
   inbound_email_domain = "reply.cornerpin.app"
   slack_client_id      = "<the Slack app's Client ID>"
   ```

   Then review and apply. The running revision keeps the Phase 1 code, which ignores the new
   settings.

   ```bash
   terraform plan -out=tfplan
   ```

   ```bash
   terraform apply tfplan
   ```

6. **Scott:** merge the Phase 2 pull request. The deploy runs migrations 0011–0017 and starts
   the new code.
7. **Scott:** connect the demo tenant. Sign in at cornerpin.app as its owner and open
   **Integrations**:
   - **Add to Slack** and pick a channel;
   - Salesforce, following [INTEGRATIONS.md](INTEGRATIONS.md).
8. **Scott: the Phase 2 gate.** Do these in Boise between 9:00 and 20:00, or the email waits
   until morning.
   1. Sign in as a buyer with an address of your own (not a `.test` one), open a lot of
      Juniper Bench, ask a question and tick **Email**.
      - The channel shows **New lead**.
      - A Lead appears in Salesforce.
      - About 15 minutes later the assistant's email arrives, quoting the lot's real price.
   2. Reply to that email. The reply shows on the lead's timeline, the lead becomes
      **Engaged**, and the assistant answers.
   3. In Slack, `/lot Juniper Bench 2-6` answers with that lot's status and price. The first
      lookup after a quiet spell can hit Slack's three-second limit while Cloud Run wakes up;
      a second try answers.

## Day to day

- Merging to `main` deploys once CI passes.
- Check the database from production's point of view:

  ```bash
  gcloud run jobs execute ops --region us-west1 --wait
  ```

  (the job's default command is `check`; its output is in the job's logs).
- Changing infrastructure: edit `infra/`, then `terraform plan` and `terraform apply`.
- Rotating a secret: run `set-secrets.sh` again (`phase2` for Phase 2's), then redeploy. Never
  rotate `integrations-key` that way: every tenant would have to connect again.

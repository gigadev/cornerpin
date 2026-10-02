# Deploying Cornerpin

How production is set up and how to change it. The decisions are in
[ADR-032](adr/032-production-deployment.md); the infrastructure is Terraform in [`infra/`](../infra).
Expected cost: about $0–2 a month, with a $5 budget alert.

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
   an API key with sending access. Sign-in emails come from `hello@cornerpin.app` unless you
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

## Day to day

- Merging to `main` deploys once CI passes.
- Check the database from production's point of view:

  ```bash
  gcloud run jobs execute ops --region us-west1 --wait
  ```

  (the job's default command is `check`; its output is in the job's logs).
- Changing infrastructure: edit `infra/`, then `terraform plan` and `terraform apply`.
- Rotating a secret: run `set-secrets.sh` again, then redeploy.

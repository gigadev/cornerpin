# Cornerpin walkthrough

A tour of everything Cornerpin does today (Phase 1), and how to run it on your own machine.
Part 1 gets it running; part 2 walks the site the way people will use it: a buyer standing on
a lot, and an owner like Ricky running the subdivision.

The screenshots come from the demo subdivision, **Juniper Bench**, a synthetic 25-lot
subdivision near Kuna, Idaho. They're taken by a script (`pnpm --filter web walkthrough`)
against a throwaway database, so they can be retaken whenever the screens change. The same
screenshots illustrate the guide inside the app, at `/help` (linked as **Help** in every
page's header and from the sign-in page), which is this tour without the developer parts.

**Contents**

1. [Running it locally](#1-running-it-locally)
2. [The public site](#2-the-public-site)
3. [Signing in](#3-signing-in)
4. [Buyers: saving lots, asking, holding](#4-buyers-saving-lots-asking-holding)
5. [The owner portal](#5-the-owner-portal)
6. [Email](#6-email)
7. [Signs and QR codes](#7-signs-and-qr-codes)
8. [Offline and installing](#8-offline-and-installing)
9. [Things to try](#9-things-to-try)

---

## 1. Running it locally

### What runs where

| Piece | Where | Started by |
| --- | --- | --- |
| Postgres + PostGIS (the database) | Docker, port 5434 | `pnpm db` |
| Mailpit (catches every email) | Docker, http://localhost:8025 | `pnpm mail` |
| API (FastAPI) | http://localhost:8000 | `pnpm api` |
| Web app (Next.js) | http://localhost:3300 | `pnpm web` |

Nothing leaves your machine except map tiles (OpenFreeMap) and the Turnstile test widget
(Cloudflare). No email is ever really sent: Mailpit catches it.

### First time

You need Docker Desktop, Node 24 or newer with pnpm (`corepack enable`), and uv (which brings
Python 3.13). From the repo root:

```bash
cp .env.example .env
```

```bash
uv sync
```

```bash
pnpm install
```

```bash
docker compose up -d
```

```bash
uv run alembic upgrade head
```

```bash
uv run python -m cornerpin.seed
```

The last two create the tables and the demo data: Demo Land Co., which owns Juniper Bench.

### Every day

Four commands from the repo root: `pnpm db` and `pnpm mail` start the database and Mailpit in
Docker, then `pnpm api` and `pnpm web` each run in their own terminal. [RUNNING.md](RUNNING.md)
has the details, stopping, and what to check when something is off.

Open http://localhost:3300/juniper-bench. Sign in as the demo owner with
`owner@demo.cornerpin.test`; the link arrives in Mailpit at http://localhost:8025. Any other
address you make up (for example `you@example.test`) becomes a buyer account. All local
accounts and URLs are listed in [TEST_ACCOUNTS.md](TEST_ACCOUNTS.md).

### Useful commands

| To | Run |
| --- | --- |
| Put the demo data back as it was | `uv run python -m cornerpin.seed` |
| Run the API tests | `uv run pytest` |
| Run the web checks and unit tests | `pnpm lint`, then `pnpm test` |
| Run the browser tests (they use their own database) | `pnpm e2e` |
| Try offline and installing (needs a production build) | see [section 8](#8-offline-and-installing) |
| Retake these screenshots | `pnpm --filter web walkthrough` |
| Stop the database and Mailpit | `pnpm stop` (your data is kept) |

---

## 2. The public site

Everything here works without signing in, and the pages work without JavaScript too (only the
map needs it), which matters on a weak signal.

### Home

![Home page](../apps/web/public/walkthrough/01-home.png)

The home page introduces the site and links to the demo subdivision and the guide. The look is
the "survey and land" theme (sage on sand, Fraunces headings), a working identity until there's
a real brand ([ADR-033](adr/033-visual-theme.md)). Visitors normally arrive at a subdivision or
lot page from a sign or a shared link, not here.

### A subdivision

![Juniper Bench: map coloured by status](../apps/web/public/walkthrough/02-subdivision.png)

`/juniper-bench`. The map shows every published lot coloured by status: green available,
orange on hold, grey sold. Clicking a lot opens its page. Lots in phase 2 aren't published, so
they don't appear at all, here or anywhere public.

Below the map is the list of lots and a filter form (status, land only or lot + home, maximum
price, minimum acres). The filters are a plain form, so a filtered list has its own address
you can share:

![Filtered to available lots with homes](../apps/web/public/walkthrough/04-filters.png)

The whole page, map to list:

<details>
<summary>Full page</summary>

![Subdivision page, full](../apps/web/public/walkthrough/03-subdivision-full.png)

</details>

### A lot

![Lot 8](../apps/web/public/walkthrough/05-lot.png)

`/juniper-bench/lots/8`. Price, status, size, listing type and home details at the top, with
the two things a buyer does next: **Contact the owner** and **Save this lot**. Below come the
photos, a map that outlines this lot among its neighbours with a **Directions** button (it
opens Google Maps to a point inside the lot), the documents (plat, survey, covenants and so
on), and the contact form.

<details>
<summary>Full page</summary>

![Lot page, full](../apps/web/public/walkthrough/06-lot-full.png)

</details>

### Contacting the owner without an account

![Contact form, signed out](../apps/web/public/walkthrough/07-contact-signed-out.png)

Anyone can ask a question: name, email, optional phone, question. Cloudflare Turnstile checks
it's a person, just above the button (left out of these screenshots: locally it's Cloudflare's
test widget, which always passes and labels itself "For testing only" in red).
The owner gets the question by email and in the portal, marked "Email not verified".
Signed-out visitors aren't asked for permission to be contacted later; that needs a verified
email address (ADR-028).

### On a phone

| Subdivision | Lot |
| --- | --- |
| ![Subdivision on a phone](../apps/web/public/walkthrough/10-mobile-subdivision.png) | ![Lot on a phone](../apps/web/public/walkthrough/11-mobile-lot.png) |

Everything is built for a phone first: most visitors will be standing on a lot, holding one.

### Link previews

![Preview card for lot 8](../apps/web/public/walkthrough/08-link-preview.png)

When someone texts or posts a lot's link, the preview shows this card: the lot, its status,
price and size. Each subdivision has one too.

---

## 3. Signing in

There are no passwords. You enter your email and click the link that arrives. A new address
gets a new account; that's the whole sign-up.

| 1. Enter your email | 2. Check your email |
| --- | --- |
| ![Sign in](../apps/web/public/walkthrough/12-sign-in.png) | ![Check your email](../apps/web/public/walkthrough/13-check-email.png) |

![The sign-in email in Mailpit](../apps/web/public/walkthrough/14-sign-in-email.png)

Locally the email lands in Mailpit (http://localhost:8025), along with every other email the
site sends. The link works once, for 15 minutes.

![Confirm sign-in](../apps/web/public/walkthrough/15-verify.png)

The link opens a page with a **Sign in** button rather than signing in by itself, because email
scanners open links. One click and you're back where you started; here, the lot page a buyer
was on when they clicked "Save this lot".

---

## 4. Buyers: saving lots, asking, holding

### Asking a question, signed in

![Contact form, signed in](../apps/web/public/walkthrough/16-contact-signed-in.png)

Signed in, the form knows who you are (the email can't be changed: it's the verified one) and
asks two more things:

- whether to **ask a question** or **ask the owner to hold this lot** (holds are only for
  available lots);
- whether the owner may **email** or **text** you about their lots beyond replying. These are
  recorded as consent rows with the time and where they came from, per owner (ADR-022), and
  are what the Phase 2 outreach will check before sending anything.

### Asking for a hold

![Hold request](../apps/web/public/walkthrough/17-hold-request.png)

No money moves online (ADR-015). The owner approves or declines; approving puts the lot on
hold. A buyer can have one pending request per lot.

### The account page

![Account](../apps/web/public/walkthrough/18-account.png)

`/account`. Saved lots with their current status and price; the email-alert switch for saved
lots; who may contact you (each permission can be withdrawn); and name, phone and time zone.
If push notifications are set up, a button to get alerts on this device appears under Alerts.

---

## 5. The owner portal

`/app`. Owners and staff of an organization manage their subdivisions here. Each organization
only ever sees its own data; the database enforces it (row-level security), not just the
screens.

### Organizations and the organization page

| Organizations | Demo Land Co. |
| --- | --- |
| ![Organizations](../apps/web/public/walkthrough/20-portal-organizations.png) | ![Organization](../apps/web/public/walkthrough/21-portal-tenant.png) |

The organizations you belong to, and your role in each (owner or staff; for now both have the
same rights). The organization page lists its subdivisions and has **Inquiries and holds**,
with a count of pending holds once there are any.

### A subdivision

<details open>
<summary>Juniper Bench in the portal</summary>

![Subdivision in the portal](../apps/web/public/walkthrough/22-portal-subdivision.png)

</details>

Every lot, including unpublished (draft) ones, with status, price, phase and acreage. Below:
phases (each released or upcoming), and the subdivision's details: name, web address,
location, time zone, description, and whether it's published. **Map and lot shapes** opens the
map editor; **Public page** opens what visitors see.

### Adding a lot

![New lot](../apps/web/public/walkthrough/23-portal-new-lot.png)

Number, phase, status, price, and land only or lot + home (choosing lot + home adds bedrooms,
bathrooms, square feet and a description). New lots start as drafts unless **Published** is
ticked. Acreage is calculated from the lot's shape once it has one.

### A lot

<details open>
<summary>Lot 8 in the portal</summary>

![Lot in the portal](../apps/web/public/walkthrough/24-portal-lot.png)

</details>

Photos (upload several at once, caption, reorder, delete; location data is stripped on upload),
documents (plat, survey, covenants, utilities, other; downloaded under their title), the
history of every status and price change with who made it and when, and the lot's details.
**Print a sign** is at the top right.

### Drawing lots on the map

![Map editor](../apps/web/public/walkthrough/25-portal-map-editor.png)

Pick a lot and draw its shape, edit corners, or import shapes from a GeoJSON file. A plat image
(a scan of the recorded plat) can be laid over the map and lined up, to trace lots over it.
Shapes are stored in PostGIS; acreage follows the shape.

### Inquiries and hold requests

<details open>
<summary>Inquiries and holds</summary>

![Inquiries and holds](../apps/web/public/walkthrough/26-portal-inquiries.png)

</details>

Pending holds first, with **Approve** and **Decline**; then every question, newest first. Each
shows how to reach the person and what they allow ("Allows: email", or "Reply only"). The
owner also gets each one by email (next section).

---

## 6. Email

Locally every email is in Mailpit. In production they're sent by Resend.

### To the owner, for each question and hold request

![Owner email](../apps/web/public/walkthrough/30-email-owner-question.png)

Sent to every owner and staff member of the organization. Replying goes straight to the buyer.

### To buyers, when a saved lot changes

![Saved-lot alert](../apps/web/public/walkthrough/31-email-saved-lot.png)

When an owner changes a published lot's status or price (or approves a hold on it), each buyer
who saved it and kept alerts on gets exactly one email. Here the owner dropped lot 8's price.

---

## 7. Signs and QR codes

![Sign page in the portal](../apps/web/public/walkthrough/27-portal-sign.png)

Each lot has a printable sign. Printed, it's just this:

![The printed sign](../apps/web/public/walkthrough/28-printed-sign.png)

The QR code opens `/q/{code}`, which looks up the lot when it's scanned and sends the visitor to
its page. The code names the lot, not its address, so signs keep working if the subdivision's
web address changes. The sign shows only what doesn't change (no price or status), since the
page is always current. The screenshots show the production address; locally the short URL
says `localhost:3300/q/…`.

A code for a lot that isn't published (or doesn't exist) says so, and nothing more:

![Code for an unlisted lot](../apps/web/public/walkthrough/09-qr-not-listed.png)

---

## 8. Offline and installing

Cornerpin is a Progressive Web App: it can be installed to a phone's home screen, and pages
you've opened keep working without a signal.

![Offline page](../apps/web/public/walkthrough/19-offline.png)

Opening any lot keeps that lot and its whole subdivision page (every lot's status, price and
shape) on the device. With no connection, those open as usual; anything else shows this page,
listing what the device has. A question written offline is kept and sent when the connection
comes back. Nothing private is ever kept: not the portal, not the account page.

When a new version of the site is published, a banner offers **Reload** instead of switching
mid-task. Each subdivision installs as its own app ("Juniper Bench · Cornerpin"), and the owner
portal as another.

The service worker that does this only runs in a production build. To try it:

```bash
pnpm --filter web build
```

```bash
pnpm --filter web exec next start --port 3300
```

(Stop `pnpm web` first.) Then in Chrome, open a lot, and in DevTools → Network
choose **Offline**. The steps are in [TEST_ACCOUNTS.md](TEST_ACCOUNTS.md#offline-and-installing-production-build-only).

---

## 9. Things to try

A route through the whole app in about twenty minutes, all local:

1. Open http://localhost:3300/juniper-bench, filter to available lots with homes, open lot 7.
2. Send a question without signing in. Find it in Mailpit (as the owner's email).
3. Click **Save this lot** and sign in with a made-up address such as `you@example.test`.
   Save the lot, ask a question allowing email, and ask to hold lot 12.
4. Open `/account` and look at saved lots and "Who may contact you".
5. In a private window, sign in as `owner@demo.cornerpin.test`. Open **Inquiries and holds**,
   approve the hold, and check that lot 12 is now on hold on the public page.
6. Still as the owner, change lot 7's price. Mailpit has the alert for your buyer address.
7. Open lot 7 in the portal, upload a photo, and see it on the public page.
8. Print a sign for lot 7, open its `/q/…` link, then change Juniper Bench's web address in the
   portal and open the same link again. (Change the address back afterwards, or re-seed.)
9. Open the map editor and redraw a lot's corner; the acreage updates.
10. When you're done: `uv run python -m cornerpin.seed` puts the demo back as it was.

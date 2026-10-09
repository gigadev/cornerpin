# ADR-049: The financing demo: a switch, five tables, synthetic data and an affordability score

- **Status:** Accepted
- **Date:** 2026-10-08
- **Applies from:** P3-05

## Context

ADR-013 puts owner financing (application, decision, loan, schedule, payments, delinquency)
in the demo tenant only, on synthetic data. Ricky doesn't offer financing. P3-05 adds the
schema, a seed, an application score "from the same scorer with a second feature set that again
excludes anything about the person", and P3-06 the screens. The plan left open:
- how a tenant gets the module;
- how money is kept exact;
- what the application score may look at;
- what the synthetic data looks like.

## Decision

- **A per-tenant switch, `tenants.financing_demo`, that only a demo tenant may have on.** A
  check constraint ties it to `is_demo`, and the seed turns it on for Demo Land Co. Every
  financing route answers 404 for a tenant without it, the same answer as for a stranger's
  tenant. The tables themselves don't check the switch; the routes do, and RLS keeps tenants
  apart as everywhere else.
- **Five tables, all tenant-owned with RLS forced:**
  - `financing_applications`: the lot, the applicant's name and email, the amount, the down
    payment, the term (5 to 30 years), a stated income band, and a status;
  - `financing_decisions`: who decided, why, and the score they saw;
  - `loans`: the principal, the rate, the term and the first due date;
  - `loan_schedules`: one row per installment, checked so payment = principal + interest;
  - `loan_payments`.

  Owners and staff read them now; P3-06 adds writing. Decisions and payments made by the seed
  have no person, marked by a NULL email.
- **Money is exact.** Amounts are `numeric(12, 2)` in the database, `Decimal` in Python, and
  two-decimal strings in the API, never floats.
  - **Schedules are fixed-rate monthly amortization.** Each month's interest is the balance
    times the monthly rate, rounded half-up to the cent, and the rest of the payment is
    principal. The last installment takes whatever principal is left, so the principal parts
    add up to exactly the amount borrowed and the balance ends at 0.00. Tests check that for
    64 combinations of amount, rate and term, and for every seeded loan.
  - **A loan's standing is worked out, not stored.** Payments fill installments in order. What
    has fallen due but isn't covered is past due, and the oldest uncovered installment sets the
    days past due.
- **The application score uses affordability, and nothing about who the buyer is.** Scott
  chose this on 2026-10-08. The features are:
  - the down payment's share of the price;
  - the term;
  - **payment-to-income**: the loan's monthly payment, at the demo's 7.5%, as a share of the
    stated income band's midpoint;
  - the lot's price band and type.

  Ability to repay is the centre of real underwriting and a permitted factor under ECOA.
  Payment-to-income is the only figure from the buyer's finances the model sees. It sees no
  name, age, location, email domain or anything like them. The personal-word check flags
  `payment_to_income` because of "income", and the test names it as the one approved
  exception, so any other such feature still fails.
- **A second model, `application-v1`, in the decisioning service.** It uses the same machinery
  as `lead-v1`, through a `Spec` per model:
  - LightGBM trained on 6,000 synthetic applications, deterministic and reproducible;
  - stated rules (`fell_behind_logit`): more down lowers the risk; a payment past a fifth of
    income and a longer term raise it;
  - monotone constraints to match;
  - a held-out AUC of 0.68.

  It lives at `POST /v1/score/application`. An application is scored once, when it's made, by
  a trigger owned by `cornerpin_leads` like ADR-045's. The score sits in `risk_scores` with
  `financing_application_id` and no lead, and a constraint allows exactly one of the two.
  Decided applications aren't scored, since the question no longer applies.
- **Synthetic data, marked as such:**
  - twelve made-up applicants, named "… (synthetic)", with emails on the reserved `.example`
    domain, so nothing can reach anyone;
  - on Juniper Bench lots no browser test uses;
  - six approved into loans on sold lots, two of them behind on payments;
  - three declined, three waiting for a decision.

  Dates count back from the day of seeding, so the loans are always part-way through and the
  late ones always late.

## Consequences

- The demo can show a whole owner-financing book (applications, scores, decisions,
  amortization, delinquency) without touching a real tenant or a real person.
- Changing the application features means changing this ADR, the test's allowed list and, for
  anything the personal-word check flags, an explicit approval.
- `application-v1`'s AUC measures how well it recovers the stated rules, not real-world credit
  risk; the metadata says the data is synthetic.

## Related

ADR-013, ADR-045, ADR-046, ADR-048

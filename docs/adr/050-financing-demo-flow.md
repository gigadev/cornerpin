# ADR-050: The financing demo's flow: applying, deciding with the score shown, lending, payments

- **Status:** Accepted
- **Date:** 2026-10-08
- **Applies from:** P3-06

## Context

P3-06 makes ADR-049's tables usable:
- a signed-in buyer applies from a lot page;
- the owner sees the score and decides, logged with the reason;
- an approval creates the loan and its schedule;
- payments are posted;
- loans behind on payments are listed;
- a decline shows its reasons in adverse-action style, as a demonstration.

The plan didn't say:
- who may apply where;
- what the buyer is told and how;
- how the loan starts;
- what limits apply to payments.

## Decision

- **Who may apply where.** Only a signed-in buyer, for a public, available, priced lot of a
  tenant with the demo on. The database enforces it:
  - the insert policy checks `app_lot_is_public` and a new `app_tenant_offers_financing`;
  - that function is owned by `cornerpin_worker`, which already reads tenants, and answers only
    yes or no for one tenant;
  - one open application per buyer per lot;
  - a buyer reads only their own applications and the decisions on them.

  Everywhere else the offer, the application and every owner route answer 404.
- **What the form asks, and what it doesn't.** It asks for the name, a down payment between 5%
  and 50% of the price in whole dollars, a term of 5 to 30 years, and a stated income range.
  It asks for no SSN, no date of birth and no credit check, and says so above the form. The
  terms are the demo's (7.5%), with a monthly payment preview worked out in the browser; the
  API's figures are the exact ones. Applying isn't lead activity: it creates no lead and no
  timeline event, since the module is a separate demonstration.
- **Deciding.**
  - The owner approves, or declines with a reason, which is required and shown to the buyer.
    The decision is logged as them, with the score on screen, as in ADR-047.
  - A score from another application is refused with 422.
  - **A decline's principal reasons are copied onto the decision when it's made.** They are
    the shown score's reasons that raised the risk, up to four, in its own words. So the
    buyer's notice is exactly what they were told, it never needs the buyer to read a score,
    and it can be audited later.
  - The buyer's account page shows it in the shape of an adverse-action notice: "financing not
    approved", the owner's reason, and the numbered principal reasons. It adds a line that a
    real notice would also name the lender and their rights under the Equal Credit Opportunity
    Act.
- **Lending.** Approval creates the loan and its whole schedule in the same transaction. The
  principal is the amount asked, at the demo's rate, with the first payment due on the 1st of
  next month (ADR-049's amortization). The lot's status doesn't change: financing approved
  isn't a sale closed, and the owner marks the lot as they would anyway.
- **Payments.** They are recorded by an owner or staff member as themselves. A payment may not
  be dated in the future, nor exceed what's still owed. Payments fill installments in order,
  and the loan's standing (current, or days behind) follows from that.
- **Screens.** The portal gets "Financing (demo)" on the tenant's page only when the switch is
  on (the tenant now says whether it is). Its page lists, in order:
  - applications, waiting ones first, each with its advisory score and reasons and the
    approve and decline controls;
  - "Behind on payments";
  - every loan.

  A loan's page shows where it stands, its payments, a form to record one, and the whole
  schedule. Every financing screen says the data is synthetic.

## Consequences

- The demo shows a credit workflow end to end, from application to score, decision, notice,
  loan, schedule, payments and delinquency, with the human decision and the advice behind it
  tied together.
- The notice is a demonstration, not compliance. Real lending would need the lender's details,
  the ECOA statement, credit reporting disclosures and more.
- A buyer's application can't be withdrawn yet; `withdrawn` exists in the schema for that.

## Related

ADR-013, ADR-047, ADR-049

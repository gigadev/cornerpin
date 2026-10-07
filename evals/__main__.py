"""Run the outreach agent evals. See evals/__init__.py, and ADR-039 for how CI runs them."""

import argparse
import os
import sys
from decimal import Decimal

from .scenarios import SCENARIOS


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m evals", description=__doc__)
    parser.add_argument("--live", action="store_true", help="use Claude (costs money)")
    parser.add_argument(
        "--record", action="store_true", help="with --live, keep the replies of passing runs"
    )
    parser.add_argument("--plant", choices=["invented-price"], help="a regression to catch")
    parser.add_argument("--only", action="append", default=[], help="run just these scenarios")
    parser.add_argument(
        "--budget",
        type=Decimal,
        default=Decimal(2),
        help="with --live, stop starting scenarios past this many dollars (default 2)",
    )
    args = parser.parse_args(argv)
    if args.record and not args.live:
        parser.error("--record needs --live")
    if args.record and args.plant:
        parser.error("never record a planted regression")
    unknown = set(args.only) - {s.name for s in SCENARIOS}
    if unknown:
        parser.error(f"no such scenario: {', '.join(sorted(unknown))}")
    return args


def dollars(amount: Decimal | None) -> str:
    return "?" if amount is None else f"${amount:.4f}"


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    # Imported here: they read settings, which prepare() points at the evals database.
    from cornerpin.core.config import get_settings
    from cornerpin.outreach.model import get_model

    from .checks import failures, listings
    from .harness import Harness, prepare
    from .models import PLANTS, EvalModel, cost, fingerprint, load, save

    owner = prepare(live=args.live)
    live_model = get_model() if args.live else None
    if args.live and live_model is None:
        print("--live needs ANTHROPIC_API_KEY in .env or the environment", file=sys.stderr)
        return 2
    model_name = get_settings().agent_model
    harness = Harness(owner)
    facts = listings(owner)
    scenarios = [s for s in SCENARIOS if not args.only or s.name in args.only]

    mode = f"live, {model_name}" if args.live else "replaying the recordings"
    plant = f", with a planted regression ({args.plant})" if args.plant else ""
    print(f"Outreach agent evals: {len(scenarios)} scenarios, {mode}{plant}\n")

    spent = Decimal(0)
    recorded_cost = Decimal(0)
    failed = 0
    rows: list[tuple[str, str, int, str]] = []
    for scenario in scenarios:
        if args.live and spent >= args.budget:
            print(f"  SKIP  {scenario.name}: the ${args.budget} budget is spent")
            failed += 1
            rows.append((scenario.name, "skipped", 0, ""))
            continue
        if args.live:
            model = EvalModel(name=model_name, live=live_model)
        else:
            recording = load(scenario.name)
            if recording is None:
                print(f"  FAIL  {scenario.name}: no recording; run with --live --record")
                failed += 1
                rows.append((scenario.name, "no recording", 0, ""))
                continue
            if recording.fingerprint != fingerprint(recording.model):
                print(
                    f"  FAIL  {scenario.name}: recorded under another prompt, tools or model;"
                    " run with --live --record"
                )
                failed += 1
                rows.append((scenario.name, "out of date", 0, ""))
                continue
            model = EvalModel(name=recording.model, replies=recording.replies)
        outcome = harness.run(scenario, model, plant=PLANTS[args.plant] if args.plant else None)
        problems = failures(outcome, facts)
        price = cost(model.name, model.usage)
        if args.live:
            spent += price or 0
        else:
            recorded_cost += price or 0
        status = "FAIL" if problems else "PASS"
        failed += bool(problems)
        print(f"  {status}  {scenario.name:<28} {model.used} model calls  {dollars(price)}")
        for problem in problems:
            print(f"          - {problem}")
        rows.append((scenario.name, status, model.used, dollars(price)))
        if args.record and not problems:
            save(scenario.name, model.name, model.replies)

    passed = len(scenarios) - failed
    money_line = (
        f"This run cost {dollars(spent)}."
        if args.live
        else f"This run cost nothing; the recordings cost {dollars(recorded_cost)} to make."
    )
    print(f"\n{passed} of {len(scenarios)} passed. {money_line}")
    if args.record:
        print("Passing scenarios' replies were saved to evals/recordings/.")
    _summary(rows, mode + plant, f"{passed} of {len(scenarios)} passed. {money_line}")
    return 1 if failed else 0


def _summary(rows: list[tuple[str, str, int, str]], mode: str, result: str) -> None:
    """A table for the GitHub Actions run page, when there is one."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [
        f"### Outreach agent evals ({mode})",
        "",
        "| Scenario | Result | Model calls | Cost |",
        "| --- | --- | --- | --- |",
    ]
    lines += [f"| {name} | {status} | {calls} | {price} |" for name, status, calls, price in rows]
    with open(path, "a", encoding="utf-8") as summary:
        summary.write("\n".join([*lines, "", result, ""]))


if __name__ == "__main__":
    sys.exit(main())

"""Run the follow-up question cases live and print each result for a person to judge; never writes to a database.

Each case in tests/follow_up_cases.json is a statement and the card's rows as a reading would give them; only new
rows are sent, as the card sends them. Prints the questions kept and dropped, whether a call was made, the tokens
used and the prompt cache hits, and flags a question of a kind the statement already answers (the case's "never").
"""

import argparse
import json
from pathlib import Path

from app.config import load_settings
from app.followups import Row, follow_ups

ROOT = Path(__file__).resolve().parent.parent
# deepseek-v4-flash at peak, US dollars per million tokens (Phase 2 prices); cache hits are billed lower.
PRICE_IN, PRICE_OUT = 0.44, 1.32


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="case ID to run, repeatable")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.llm_api_key:
        print("LLM_API_KEY is not configured. Live cases have not been run.")
        return 2
    cases = json.loads((ROOT / "tests" / "follow_up_cases.json").read_text())
    ran = met = calls = already = tokens_in = tokens_out = cached = 0
    for case in cases:
        if args.case and case["id"] not in args.case:
            continue
        rows = [Row(item["row"], item["name"], item.get("url"), item.get("personal", False))
                for item in case["rows"] if not item.get("existing")]
        result = follow_ups(case["text"], rows, settings) if rows else None
        questions = result.questions if result else []
        called = bool(result and result.called)
        ran += 1
        calls += called
        said = [item for item in questions if [item["row"], item["kind"]] in case["never"]]
        already += len(said)
        fixed = sum(item["fixed"] for item in questions)
        problems = []
        if len(questions) > case["most"]:
            problems.append(f"{len(questions)} questions, at most {case['most']}")
        if len(questions) < case.get("least", 0):
            problems.append(f"{len(questions)} questions, at least {case['least']}")
        if fixed != case["fixed"]:
            problems.append(f"{fixed} fixed, expected {case['fixed']}")
        if called != case["call"]:
            problems.append("a call was made" if called else "no call was made")
        if said:
            problems.append(f"{len(said)} asked what the statement already says")
        if case.get("kinds") and any(item["kind"] not in case["kinds"] for item in questions if not item["fixed"]):
            problems.append(f"a kind outside {case['kinds']}")
        if case.get("want") and not any([item["row"], item["kind"]] in case["want"] for item in questions):
            problems.append(f"none of {case['want']}")
        met += not problems
        print(f"\n{case['id']} {'as expected' if not problems else 'NOT AS EXPECTED'}: {case['name']}")
        print(f"  expect  {case['expect']}")
        for item in questions:
            print(f"  asked   {item['row']} '{item['name']}' {item['kind']}{' (fixed)' if item['fixed'] else ''}: {item['text']}")
        for item in (result.rejected if result else []):
            print(f"  dropped {json.dumps(item, ensure_ascii=False)}")
        for problem in problems:
            print(f"  problem {problem}")
        status = result.status if result else "no new row"
        usage = (result.usage if result else None) or {}
        tokens_in += usage.get("prompt_tokens", 0)
        tokens_out += usage.get("completion_tokens", 0)
        cached += usage.get("prompt_cache_hit_tokens", 0)
        print(f"  status  {status}; call {'yes' if called else 'no'}" + (
            f"; tokens in {usage.get('prompt_tokens')}, cache hits {usage.get('prompt_cache_hit_tokens')}, "
            f"out {usage.get('completion_tokens')}" if usage else ""))
    print(f"\n{met} of {ran} cases as expected; {calls} calls; {already} questions on what a statement already says.")
    if calls:
        print(f"Tokens: {tokens_in} in ({cached} cache hits), {tokens_out} out; per call {tokens_in // calls} in "
              f"({cached // calls} cache hits), {tokens_out // calls} out.")
        cost = (tokens_in * PRICE_IN + tokens_out * PRICE_OUT) / 1e6 / calls * 100
        print(f"About {cost:.2f} US cents a call at peak before cache discounts.")
    return 0 if met == ran else 1


if __name__ == "__main__":
    raise SystemExit(main())

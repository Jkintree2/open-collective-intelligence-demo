"""Run the evidence check cases live and print each result for a person to judge; never writes to a database.

Fixture cases read a saved page from tests/fixtures/pages instead of the web. Prints the tokens
used, so the cost per link can be measured.
"""

import argparse
import json
from pathlib import Path

from app import check
from app.config import load_settings
from app.fetch_page import Page, cut, fetch, html_text

ROOT = Path(__file__).resolve().parent.parent


def fixture_fetcher(name: str):
    def fetcher(url, about="", **kwargs):
        text, title, description, published = html_text((ROOT / "tests" / "fixtures" / "pages" / name).read_text())
        return Page("ok", url, cut(text, about), title, description, published)
    return fetcher


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="case ID to run, repeatable")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.llm_api_key:
        print("LLM_API_KEY is not configured. Live cases have not been run.")
        return 2
    cases = json.loads((ROOT / "tests" / "check_cases.json").read_text())
    ran = met = tokens_in = tokens_out = wrong_way = 0
    for case in cases:
        if args.case and case["id"] not in args.case:
            continue
        fetcher = fixture_fetcher(case["fixture"]) if case.get("fixture") else fetch
        result = check.check_evidence(case["url"], case["evidence"], case["about"], case["statement"], settings,
                                      writer_says=case["writer_says"], fetcher=fetcher)
        ran += 1
        ok = result.verdict in case["expect"]
        met += ok
        wrong_way += {result.verdict, case["expect"][0]} == {"supports", "refutes"}
        usage = result.usage or {}
        tokens_in += usage.get("prompt_tokens", 0)
        tokens_out += usage.get("completion_tokens", 0)
        print(f"\n{case['id']} {'as expected' if ok else 'NOT AS EXPECTED'}: {case['name']}")
        print(f"  verdict {result.verdict} (expected {' or '.join(case['expect'])})")
        if result.quote:
            print(f"  quote   {result.quote}")
        if result.reason:
            print(f"  reason  {result.reason}")
        if result.source:
            print(f"  source  {json.dumps(result.source)}")
        if any(result.suggested.values()):
            print(f"  also    {json.dumps({k: [r['name'] for r in v] for k, v in result.suggested.items() if v})}")
        if usage:
            print(f"  tokens  {usage.get('prompt_tokens')} in, {usage.get('completion_tokens')} out")
    print(f"\n{met} of {ran} as expected; {wrong_way} read the wrong way round (supports for refutes or back).")
    print(f"Tokens: {tokens_in} in, {tokens_out} out over {ran} cases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

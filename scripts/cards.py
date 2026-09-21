"""Print the acceptance cases for human assessment; never writes to a database."""

import argparse
import json
from pathlib import Path

from app import extract as reading
from app.config import load_settings
from app.extract import Candidates
from app.text import make_key, sentences

ROOT = Path(__file__).resolve().parent.parent


def seed_candidates() -> Candidates:
    seed = json.loads((ROOT / "seed" / "seed.json").read_text())
    issues = {make_key(item["name"]): {"name": item["name"], "parent_key": make_key(item["parent"]) if item.get("parent") else None} for item in seed["issues"]}
    solutions, evidence, homes = {}, {}, {}
    for post in seed["posts"]:
        for item in post["solutions"]:
            item_key = make_key(item["name"])
            solutions[item_key] = item["name"]
            homes.setdefault(item_key, [])
            if item["for_issue"] not in homes[item_key]:
                homes[item_key].append(item["for_issue"])
        evidence.update({make_key(item["name"]): item["name"] for item in post["evidence"]})
    return Candidates(issues, solutions, evidence, homes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="case ID to run, repeatable")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.llm_api_key:
        print("LLM_API_KEY is not configured. Live cases have not been run.")
        return 2
    cases = json.loads((ROOT / "tests" / "extraction_cases.json").read_text())
    for case in cases:
        if args.case and case["id"] not in args.case:
            continue
        candidates = seed_candidates() if case["context"] != "empty" else Candidates.empty()
        if case["context"] == "drug":
            candidates.issues["drug dealing problem"] = {"name": "Drug dealing problem", "parent_key": None}
            candidates.solutions["decriminalize drug sales"] = "Decriminalize drug sales"
            candidates.solutions["treat drug use as medical issue"] = "Treat drug use as medical issue"
        if case["context"] == "stlouis":
            for name in ("Data centers", "Platform for digital democracy", "Downtown St Louis revitalization"):
                candidates.issues[make_key(name)] = {"name": name, "parent_key": None}
        text = case["text"]
        if case.get("words"):
            words = text.split()
            text = " ".join((words * (case["words"] // len(words) + 1))[:case["words"]])
        print(f"\nCase {case['id']}: {case['name']}\nExpected: {case['expect']}")
        if len(text) > 4000:
            print(f"Too long ({len(text)} characters); provider not called.")
            continue
        result = reading.extract(text, case.get("display_name", "Tester"), candidates, settings,
                                 writing_about=case.get("writing_about"))
        if result is None:
            print("No result. Review provider status before continuing.")
            return 1
        print(json.dumps({"payload": result.payload.model_dump(), "model": result.model,
                          "latency_ms": result.latency_ms}, ensure_ascii=False, indent=2))
        print("\n".join(sentences(result.payload, case.get("display_name", "Tester"))))
    print("\nHuman review required: record pass/fail for every case run; all three variants must pass case 6.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

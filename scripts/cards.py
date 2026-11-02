"""Print the acceptance cases for human assessment, or with --check run each one against its machine checks and
pass mark (docs/planning/05_extraction.md, "The reading-quality loop"); never writes to a database."""

import argparse
import json
import subprocess
import sys
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import extract as reading
from app.config import load_settings
from app.extract import Candidates
from app.text import make_key, sentences
from scripts.case_checks import failures, validate

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "extraction_cases.json"
TEXT_LIMIT = 4000


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


def load_names(path: Path) -> Candidates:
    """The live names: a file holding the body of GET /api/candidates, saved outside the repository."""
    return Candidates(**json.loads(Path(path).read_text()))


def load_cases(extra: list[Path] = ()) -> list[dict]:
    """The repository's cases, then each extra file's (the private live cases); an id may not repeat."""
    cases = json.loads(CASES.read_text())
    seen = {case["id"] for case in cases}
    for path in extra:
        for case in json.loads(Path(path).read_text()):
            if case["id"] in seen:
                raise ValueError(f"case id {case['id']} is used twice")
            seen.add(case["id"])
            cases.append(case)
    return cases


def context_candidates(case: dict, names: Candidates | None) -> Candidates | None:
    """The record a case is read against; for `live` the snapshot of the live names, None without one."""
    if case["context"] == "live":
        return names
    candidates = seed_candidates() if case["context"] != "empty" else Candidates.empty()
    if case["context"] == "drug":
        candidates.issues["drug dealing problem"] = {"name": "Drug dealing problem", "parent_key": None}
        candidates.solutions["decriminalize drug sales"] = "Decriminalize drug sales"
        candidates.solutions["treat drug use as medical issue"] = "Treat drug use as medical issue"
    if case["context"] in ("stlouis", "moratorium"):
        for name in ("Data centers", "Downtown St Louis revitalization"):
            candidates.issues[make_key(name)] = {"name": name, "parent_key": None}
    if case["context"] == "moratorium":  # John's live moratorium solution, 2 November 2026, on top of stlouis
        name = "Moratorium on building new data centers"
        candidates.solutions[make_key(name)] = name
        candidates.solution_issues[make_key(name)] = ["Data centers"]
    if case["context"] == "world":  # the live record's shape, 2 November 2026: no veto issue, the veto solution
        candidates.issues.pop("security council veto", None)  # under Need for world government
        candidates.solution_issues["limit or abolish the security council veto"] = ["Need for world government"]
    if case["context"] == "consensus":  # John's live consensus solution, 31 October 2026, on top of the seed
        name = "Methods of collective decision making"
        candidates.issues[make_key(name)] = {"name": name, "parent_key": None}
        candidates.solutions["decisions should be made by consensus"] = "Decisions should be made by consensus"
        candidates.solution_issues["decisions should be made by consensus"] = ["Need for world government", name]
    return candidates


def case_text(case: dict) -> str:
    text = case["text"]
    if case.get("words"):
        words = text.split()
        text = " ".join((words * (case["words"] // len(words) + 1))[:case["words"]])
    return text


def writing_about(case: dict):
    # An issue's key, or (GitHub issue 55) {"solution": key} or {"evidence": key}.
    about = case.get("writing_about")
    return next(iter(about.items())) if isinstance(about, dict) else about


def differs_at(ref: str) -> list[str]:
    """The files under app/ other than extract.py that differ at `ref`: both readings run them as they are today."""
    out = subprocess.run(["git", "diff", "--name-only", ref, "--", "app", ":(exclude)app/extract.py"], cwd=ROOT,
                         check=True, capture_output=True, text=True).stdout
    return out.split()


def reading_at(ref: str) -> types.ModuleType:
    """app/extract.py as it is at `ref`, beside today's. It imports today's app/payload.py."""
    source = subprocess.run(["git", "show", f"{ref}:app/extract.py"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout
    module = types.ModuleType("extract_at_ref")
    module.__file__ = f"{ref}:app/extract.py"
    sys.modules[module.__name__] = module  # dataclasses look their module up while the source runs
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def run_case(case: dict, candidates: Candidates, readings: list, runs: int, settings, pool) -> list[dict]:
    """Every run of every reading is sent at once, so readings compared side by side are read at the same moment."""
    text, about = case_text(case), writing_about(case)
    name = case.get("display_name", "Tester")
    columns = [[pool.submit(each.extract, text, name, candidates, settings, writing_about=about) for _ in range(runs)]
               for each in readings]
    results = []
    for column in columns:
        passed, no_answer, misses = 0, 0, []
        for number, future in enumerate(column, 1):
            result = future.result()
            if result is None:
                no_answer += 1
            elif lines := failures(result.payload.model_dump(), case["checks"]):
                misses.append(f"run {number}: " + "; ".join(lines))
            else:
                passed += 1
        results.append({"passed": passed, "runs": runs, "no_answer": no_answer, "misses": misses})
    return results


def check(cases: list[dict], names: Candidates | None, readings: list, runs: int, settings,
          against: str | None = None) -> int:
    """Run each case `runs` times and print one line a case. 0: every case met its mark (and, beside `against`,
    none is worse); 1: a case missed or is worse; 3: a case missed only for runs with no answer. A case with a
    `known_miss` (a misreading not fixed yet, said in words) is reported on every run and never fails it."""
    for case in cases:
        if case.get("checks") != "local":
            validate(case.get("checks"))
        if "known_miss" in case and not (isinstance(case["known_miss"], str) and case["known_miss"].strip()):
            raise ValueError(f"case {case['id']}: known_miss must say what the misreading is")
    met = missed = skipped = worse = known = 0
    no_answer = no_answer_only = 0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for case in cases:
            label = f"case {case['id']}"
            if case.get("checks") == "local":
                ok = len(case_text(case)) > TEXT_LIMIT
                met, missed = met + ok, missed + (not ok)
                print(f"{label}   local   {'met' if ok else 'MISSED: under the length limit'}")
                continue
            candidates = context_candidates(case, names)
            if candidates is None:
                skipped += 1
                print(f"{label}   skipped (needs --names)")
                continue
            results = run_case(case, candidates, readings, runs, settings, pool)
            now, mark = results[0], min(case.get("pass", runs), runs)
            no_answer += sum(result["no_answer"] for result in results)
            line = f"{label}   {now['passed']}/{runs}"
            if against:
                line = f"{label}   now {now['passed']}/{runs}   {against} {results[1]['passed']}/{runs}"
                if now["passed"] + now["no_answer"] < results[1]["passed"]:
                    worse += 1
                    line += "   WORSE"
            if now["passed"] >= mark:
                met += 1
                line += "   met" + (" (the known miss was not seen)" if case.get("known_miss") else "")
            elif case.get("known_miss"):
                known += 1
                line += f"   MISSED (known: {case['known_miss']}) " + " | ".join(now["misses"])
            elif now["passed"] + now["no_answer"] >= mark:
                no_answer_only += 1
                line += "   MISSED: no answer"
            else:
                missed += 1
                line += "   MISSED: " + " | ".join(now["misses"])
            if now["no_answer"]:
                line += f"   ({now['no_answer']} with no answer)"
            print(line)
    total = met + missed + no_answer_only + known
    summary = (f"\n{met} of {total} cases met their mark; {known} known miss{'' if known == 1 else 'es'}; "
               f"{skipped} skipped (needs --names); "
               f"{no_answer} run{'' if no_answer == 1 else 's'} with no answer")
    print(summary + (f"; {worse} worse than {against}" if against else ""))
    if missed or worse:
        return 1
    return 3 if no_answer_only else 0


def show(cases: list[dict], names: Candidates | None, settings) -> int:
    """Print each case's card for a person to judge, as before --check existed."""
    for case in cases:
        candidates = context_candidates(case, names)
        text = case_text(case)
        print(f"\nCase {case['id']}: {case['name']}\nExpected: {case['expect']}")
        if candidates is None:
            print("Needs --names; provider not called.")
            continue
        if len(text) > TEXT_LIMIT:
            print(f"Too long ({len(text)} characters); provider not called.")
            continue
        result = reading.extract(text, case.get("display_name", "Tester"), candidates, settings,
                                 writing_about=writing_about(case))
        if result is None:
            print("No result. Review provider status before continuing.")
            return 1
        print(json.dumps({"payload": result.payload.model_dump(), "model": result.model,
                          "latency_ms": result.latency_ms}, ensure_ascii=False, indent=2))
        print("\n".join(sentences(result.payload, case.get("display_name", "Tester"))))
    print("\nHuman review required: record pass/fail for every case run; all three variants must pass case 6.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="case ID to run, repeatable")
    parser.add_argument("--check", action="store_true", help="run the machine checks against each pass mark")
    parser.add_argument("--runs", type=int, default=3, help="runs a case with --check (default 3)")
    parser.add_argument("--names", type=Path, help="the live names, saved from GET /api/candidates")
    parser.add_argument("--cases", type=Path, action="append", default=[], help="more cases, repeatable")
    parser.add_argument("--against", help="a commit whose reading runs beside today's, at the same moment")
    args = parser.parse_args()
    settings = load_settings()
    if not settings.llm_api_key:
        print("LLM_API_KEY is not configured. Live cases have not been run.")
        return 2
    cases = [case for case in load_cases(args.cases) if not args.case or case["id"] in args.case]
    names = load_names(args.names) if args.names else None
    if not args.check:
        return show(cases, names, settings)
    readings = [reading]
    if args.against:
        if changed := differs_at(args.against):
            print(f"These differ at {args.against} and run as they are today on both sides: {', '.join(changed)}")
        readings.append(reading_at(args.against))
    return check(cases, names, readings, args.runs, settings, against=args.against)


if __name__ == "__main__":
    raise SystemExit(main())

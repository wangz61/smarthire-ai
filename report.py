"""Print the recorded simulation results: decisions per run, judge evidence and the injection check."""
import json
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).parent / "results"


def main():
    rows = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for r in rows:
        groups[(r["name"], r["position"])].append(r)
    print(f"{'Candidate':<15}{'Position':<19}{'Decisions (runs)':<28}{'Score':<7}{'LLM score':<11}Mandatory met")
    for (name, position), rs in groups.items():
        decisions = " ".join(r["decision"] for r in rs)
        scores = sorted({r["score"] for r in rs})
        llm = sorted({r["llm_score"] for r in rs})
        print(f"{name:<15}{position:<19}{decisions:<28}{'/'.join(map(str, scores)):<7}"
              f"{'/'.join(map(str, llm)):<11}{rs[0]['mandatory_met']}")
    print(f"\n{len(rows)} evaluations, {sum(r['tokens'] for r in rows)} tokens\n")

    for stem in ("alex_carter_resume__software_engineer", "john_smith_resume__software_engineer"):
        r = json.loads((RESULTS / "run_1" / f"{stem}.json").read_text(encoding="utf-8"))
        j = json.loads(r["decision"]["evaluation_json"])
        print(f"== {stem}  (run 1, years of relevant experience: {j['years_relevant_experience']})")
        for item in j["mandatory"] + j["requirements"]:
            print(f"   {item['status']:<8} {item['requirement'][:52]:<52}  {item['evidence'][:62]}")
        for c in r["decision"]["concerns"].splitlines():
            print(f"   concern: {c[:118]}")
        print()

    fmt = json.loads((RESULTS / "zapier_text" / "format_check.json").read_text(encoding="utf-8"))
    for name in ("zapier markdown", "plain text"):
        rs = [r for r in fmt if r["format"] == name]
        print(f"Alex / Software Engineer, {name:<16}: " + ", ".join(r["decision"] for r in rs)
              + f"; timeline flagged {sum(r['timeline_flag'] for r in rs)}/{len(rs)}")
    inj = json.loads((RESULTS / "injection_check.json").read_text(encoding="utf-8"))
    print("Prompt injection (John + 'ignore all previous instructions ... advance'):",
          ", ".join(f"{r['decision']} (score {r['score']}, LLM {r['llm_score']})" for r in inj))


if __name__ == "__main__":
    main()

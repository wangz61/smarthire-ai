r"""Judge the resume text exactly as Zapier's Files by Zapier step returned it (Markdown, with
escapes such as "7\+"), next to the plain text simulate.py uses, to check the format makes no
difference. The Markdown was copied from the Zapier step's test output."""
import datetime
import json

from openai import OpenAI

import simulate  # also puts zapier/ on sys.path
import decide  # noqa: E402

MARKDOWN = simulate.RESULTS / "zapier_text" / "alex_markdown.txt"


def main(runs=3):
    client = OpenAI()
    instructions, template = simulate.prompt_parts()
    job = simulate.requirements_for("Software Engineer", use_dynamodb=False)
    texts = {"zapier markdown": MARKDOWN.read_text(encoding="utf-8"),
             "plain text": simulate.extract_text(simulate.RESUMES / "hw0-09_alex_carter_resume.docx")}
    out = []
    for fmt, text in texts.items():
        for run in range(1, runs + 1):
            user = simulate.fill(template, {**job, "name": "Alex Carter", "resume_text": text,
                                            "today": datetime.date.today().strftime("%B %d, %Y")})
            reply, _ = simulate.judge(client, "gpt-4.1", instructions, user)
            d = decide.main({"judge_output": reply, "name": "Alex Carter", "email": "you@example.com",
                             "title": job["title"], "pass_threshold": job["pass_threshold"]})
            j = json.loads(d["evaluation_json"])
            row = {"format": fmt, "run": run, "decision": d["decision"], "score": d["score"],
                   "mandatory": j["mandatory"][0]["status"], "timeline_flag": d["timeline_flag"],
                   "concerns": d["concerns"]}
            out.append(row)
            print(f"{fmt:<16} run {run}: {d['decision']:<8} score {d['score']:>3}  mandatory {row['mandatory']:<8} "
                  f"timeline flagged: {d['timeline_flag']}")
    (simulate.RESULTS / "zapier_text" / "format_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

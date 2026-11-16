"""Run the SmartHire Zap locally, step for step, before building it in Zapier.

    [1] form response      -> one row per (resume, position) below
    [4] Text From File     -> extract_text(): the .docx text, as Files by Zapier would return it
    [5] get_requirements   -> zapier/get_requirements.py (from DynamoDB with --dynamodb, else the local JSON)
    [6] Send Prompt        -> zapier/judge_prompt.md, sent to OpenAI exactly as written there
    [7] decide             -> zapier/decide.py
    [9] Paths + Gmail      -> the email is written to results/outbox/, never sent

Usage:
    python simulate.py                  # 2 resumes x 2 positions, 3 runs each
    python simulate.py --runs 1 --dynamodb
"""
import argparse
import datetime
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "zapier"))
import decide  # noqa: E402
import get_requirements  # noqa: E402

RESUMES = ROOT / "data" / "resumes"
RESULTS = ROOT / "results"
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# The form answers for each test submission. The email is a placeholder: nothing is sent locally,
# and in Zapier you should submit with your own address.
CANDIDATES = {
    "hw0-09_alex_carter_resume.docx": {"name": "Alex Carter", "email": "you+alex@example.com"},
    "hw0-09_john_smith_resume.docx": {"name": "John W. Smith", "email": "you+john@example.com"},
}
POSITIONS = ["Software Engineer", "AI Engineer"]


def extract_text(path):
    """Paragraph text of a .docx (body and tables), one paragraph per line."""
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    lines = []
    for p in root.iter(f"{W}p"):
        parts = []
        for node in p.iter():
            if node.tag == f"{W}t":
                parts.append(node.text or "")
            elif node.tag == f"{W}tab":
                parts.append("\t")
            elif node.tag in (f"{W}br", f"{W}cr"):
                parts.append("\n")
        text = "".join(parts).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def prompt_parts():
    """(instructions, user template) from the two code blocks in judge_prompt.md."""
    blocks = re.findall(r"```\n(.*?)\n```", (ROOT / "zapier" / "judge_prompt.md").read_text(encoding="utf-8"), re.S)
    if len(blocks) != 2:
        raise ValueError("judge_prompt.md must contain exactly two code blocks")
    return blocks[0], blocks[1]


def fill(template, fields):
    def sub(m):
        if m.group(1) not in fields:
            raise KeyError(f"no value for {{{{{m.group(1)}}}}}")
        return str(fields[m.group(1)])
    return re.sub(r"\{\{(\w+)\}\}", sub, template)


def requirements_for(position, use_dynamodb):
    if use_dynamodb:
        return get_requirements.main({
            "position": position,
            "aws_access_key": os.environ["AWS_ACCESS_KEY_ID"],
            "aws_secret_key": os.environ["AWS_SECRET_ACCESS_KEY"],
            "aws_region": os.environ.get("AWS_REGION", "us-east-1"),
            "table": "smarthire_job_requirements",
        })
    jobs = json.loads((ROOT / "data" / "job_requirements.json").read_text(encoding="utf-8"))
    key = get_requirements.position_key(position)
    return get_requirements.to_output(next(j for j in jobs if j["position"] == key))


def judge(client, model, instructions, user):
    response = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": user}])
    return response.choices[0].message.content, response.usage.total_tokens


def run_one(client, model, resume, form, position, use_dynamodb):
    resume_text = extract_text(RESUMES / resume)
    job = requirements_for(position, use_dynamodb)
    instructions, template = prompt_parts()
    today = datetime.date.today().strftime("%B %d, %Y")
    user = fill(template, {**job, "name": form["name"], "resume_text": resume_text, "today": today})
    reply, tokens = judge(client, model, instructions, user)
    result = decide.main({"judge_output": reply, "name": form["name"], "email": form["email"],
                          "title": job["title"], "pass_threshold": job["pass_threshold"]})
    return {"resume": resume, "position": position, "requirements": job, "judge_output": reply,
            "tokens": tokens, "decision": result}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="gpt-4.1")
    ap.add_argument("--dynamodb", action="store_true", help="read requirements from DynamoDB (AWS_* env vars)")
    args = ap.parse_args(argv)

    from openai import OpenAI
    client = OpenAI()
    outbox = RESULTS / "outbox"
    outbox.mkdir(parents=True, exist_ok=True)
    rows = []
    for run in range(1, args.runs + 1):
        for resume, form in CANDIDATES.items():
            for position in POSITIONS:
                r = run_one(client, args.model, resume, form, position, args.dynamodb)
                d = r["decision"]
                stem = f"{Path(resume).stem.replace('hw0-09_', '')}__{get_requirements.position_key(position)}"
                (RESULTS / f"run_{run}").mkdir(exist_ok=True)
                (RESULTS / f"run_{run}" / f"{stem}.json").write_text(json.dumps(r, indent=2, ensure_ascii=False),
                                                                    encoding="utf-8")
                if run == 1 and d["decision"] != "needs_review":
                    (outbox / f"{stem}.txt").write_text(
                        f"To: {d['email_to']}\nSubject: {d['email_subject']}\n\n{d['email_body']}\n", encoding="utf-8")
                rows.append((run, form["name"], position, d["decision"], d["score"], d["llm_score"],
                             d["llm_recommendation"], d["mandatory_met"], r["tokens"]))
                print(f"run {run}  {form['name']:<14} {position:<18} {d['decision']:<8} score {d['score']:>3}  "
                      f"(LLM {d['llm_score']}, {d['llm_recommendation']}, mandatory met: {d['mandatory_met']})",
                      flush=True)
    (RESULTS / "summary.json").write_text(json.dumps(
        [dict(zip(("run", "name", "position", "decision", "score", "llm_score", "llm_recommendation",
                   "mandatory_met", "tokens"), row)) for row in rows], indent=2), encoding="utf-8")
    print(f"\n{len(rows)} evaluations, {sum(r[-1] for r in rows)} tokens. Results in {RESULTS}")


if __name__ == "__main__":
    main()

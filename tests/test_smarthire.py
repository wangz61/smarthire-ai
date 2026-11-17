import datetime
import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dynamodb"))

import build_setup  # noqa: E402
import simulate  # noqa: E402  (also puts zapier/ on sys.path)
import decide  # noqa: E402
import get_requirements as gr  # noqa: E402

NOW = datetime.datetime(2026, 11, 16, 12, 30, 45, tzinfo=datetime.timezone.utc)


def judged(mandatory=("met",), others=("met", "met"), score=90, **extra):
    data = {"candidate_name": "A", "years_relevant_experience": 5,
            "mandatory": [{"requirement": f"m{i}", "status": s, "evidence": "e"} for i, s in enumerate(mandatory)],
            "requirements": [{"requirement": f"r{i}", "status": s, "evidence": "e"} for i, s in enumerate(others)],
            "strengths": ["Strong Python."], "concerns": [], "overall_score": score,
            "recommendation": "advance", "summary": "ok"}
    data.update(extra)
    return data


def run_decide(judge_output, **form):
    return decide.main({"judge_output": judge_output, "name": "Alex Carter", "email": "a@example.com",
                        "title": "Software Engineer", "pass_threshold": "70", **form})


# ---- resume text (Files by Zapier: Text From File) ------------------------------------------------------

def test_extract_text_matches_python_docx():
    import docx
    for path in simulate.RESUMES.glob("*.docx"):
        expected = "\n".join(p.text.strip() for p in docx.Document(path).paragraphs if p.text.strip())
        assert simulate.extract_text(path) == expected


def test_extract_text_content():
    alex = simulate.extract_text(simulate.RESUMES / "hw0-09_alex_carter_resume.docx")
    assert alex.startswith("Alex Carter\nSoftware Engineer")
    assert "7+ years of experience" in alex and "Graduated: 2024" in alex


# ---- DynamoDB (get_requirements.py) ---------------------------------------------------------------------

def test_sigv4_matches_botocore():
    from unittest import mock

    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    body = json.dumps({"TableName": "t", "Key": {"position": {"S": "software_engineer"}}})
    host = "dynamodb.us-east-1.amazonaws.com"
    ours = gr.sign("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY", "us-east-1", host, gr.TARGET, body, NOW)

    request = AWSRequest(method="POST", url=f"https://{host}/", data=body,
                         headers={"Content-Type": "application/x-amz-json-1.0", "X-Amz-Target": gr.TARGET})
    with mock.patch("botocore.auth.get_current_datetime", return_value=NOW.replace(tzinfo=None)):
        SigV4Auth(Credentials("AKIDEXAMPLE", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"), "dynamodb",
                  "us-east-1").add_auth(request)
    assert request.headers["X-Amz-Date"] == ours["x-amz-date"] == "20261116T123045Z"
    assert request.headers["Authorization"] == ours["authorization"]


def test_marshal_unmarshal_round_trip():
    for job in json.loads((ROOT / "data" / "job_requirements.json").read_text(encoding="utf-8")):
        item = build_setup.item(job)
        assert {k: gr.unmarshal(v) for k, v in item.items()} == job
    assert gr.unmarshal({"N": "0.5"}) == 0.5
    assert gr.unmarshal({"SS": ["a", "b"]}) == ["a", "b"]


class FakeResponse:
    def __init__(self, status, payload):
        self.status_code, self._payload, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._payload


def test_get_item_request_and_output():
    job = json.loads((ROOT / "data" / "job_requirements.json").read_text(encoding="utf-8"))[0]
    sent = {}

    def post(url, data, headers, timeout):
        sent.update(url=url, body=json.loads(data), headers=headers)
        return FakeResponse(200, {"Item": build_setup.item(job)})

    out = gr.to_output(gr.get_item("Software Engineer", "AK", "SK", "us-west-2", "jobs", NOW, post))
    assert sent["url"] == "https://dynamodb.us-west-2.amazonaws.com/"
    assert sent["body"] == {"TableName": "jobs", "Key": {"position": {"S": "software_engineer"}}}
    assert sent["headers"]["x-amz-target"] == "DynamoDB_20120810.GetItem"
    assert out["title"] == "Software Engineer" and out["pass_threshold"] == 70
    assert out["requirements_block"].splitlines()[0] == "1. [MANDATORY] 3+ years of relevant experience"
    assert out["requirements_block"].splitlines()[-1] == "7. Strong communication skills"


def test_get_item_errors():
    with pytest.raises(LookupError, match="no job requirements for position 'chef'"):
        gr.get_item("Chef", "AK", "SK", "us-east-1", "jobs", NOW, lambda *a, **k: FakeResponse(200, {}))
    with pytest.raises(RuntimeError, match="403"):
        gr.get_item("Chef", "AK", "SK", "us-east-1", "jobs", NOW,
                    lambda *a, **k: FakeResponse(403, {"message": "denied"}))


def test_position_key():
    assert gr.position_key("  Software Engineer ") == "software_engineer"
    assert gr.position_key("AI Engineer") == "ai_engineer"


def test_setup_script_and_policy():
    script = build_setup.setup_script()
    assert script.count("create-table") == 2 and script.count("put-item") == 2
    assert "Bachelor'\"'\"'s" in script                     # quote inside a single-quoted argument
    policy = build_setup.iam_policy()
    actions = {a for s in policy["Statement"] for a in s["Action"]}
    assert actions == {"dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DescribeTable", "dynamodb:ListTables"}


# ---- decision (decide.py) -------------------------------------------------------------------------------

@pytest.mark.parametrize("mandatory, others, decision, score", [
    (("met",), ("met", "met", "met"), "advance", 100),
    (("met",), ("met", "partial", "not_met"), "reject", 62),     # mandatory met, but 62 < 70
    (("partial",), ("met", "met", "met"), "reject", 88),         # mandatory not fully met
    (("met",), ("not_met", "not_met", "partial"), "reject", 38),
    (("met", "met"), ("partial", "partial"), "advance", 75),
])
def test_decision_rule(mandatory, others, decision, score):
    result = run_decide(json.dumps(judged(mandatory, others)))
    assert (result["decision"], result["score"]) == (decision, score)


def test_threshold_boundary():
    data = json.dumps(judged(("met",), ("met", "met", "partial", "partial", "partial", "not_met")))  # 4.5 / 7 -> 64
    assert run_decide(data)["score"] == 64
    assert run_decide(data, pass_threshold="64")["decision"] == "advance"
    assert run_decide(data, pass_threshold="65")["decision"] == "reject"


def test_llm_recommendation_does_not_override_rule():
    # The LLM says advance, but a mandatory requirement is not met.
    result = run_decide(json.dumps(judged(("not_met",), ("met", "met"), score=100, recommendation="advance")))
    assert result["decision"] == "reject" and result["llm_recommendation"] == "advance"


def test_fenced_and_wrapped_json_is_accepted():
    body = json.dumps(judged())
    for text in (f"```json\n{body}\n```", f"Here is the evaluation:\n{body}\nThanks."):
        assert run_decide(text)["decision"] == "advance"


@pytest.mark.parametrize("text, message", [
    ("", "no JSON object"),
    ("I cannot evaluate this.", "no JSON object"),
    ("{not json}", "invalid JSON"),
    (json.dumps(judged(mandatory=())), "'mandatory' is empty"),
    (json.dumps({**judged(), "requirements": [{"status": "great"}]}), "no valid status"),
    (json.dumps(judged(score=150)), "overall_score"),
])
def test_bad_judge_output_goes_to_review(text, message):
    result = run_decide(text)
    assert result["decision"] == "needs_review" and message in result["summary"]
    assert result["email_subject"] == "" and result["email_body"] == ""


def test_emails():
    adv = run_decide(json.dumps(judged()))
    assert adv["email_to"] == "a@example.com"
    assert adv["email_subject"] == "Next steps for your Software Engineer application at SmartHire"
    assert adv["email_body"].startswith("Hi Alex,") and "Strong Python" in adv["email_body"]
    rej = run_decide(json.dumps(judged(("not_met",))), company="Acme")
    assert rej["email_subject"] == "Your Software Engineer application at Acme"
    assert "not to move forward" in rej["email_body"] and "Strong Python" not in rej["email_body"]


def test_runs_as_zapier_code_step():
    """Zapier provides `input_data` and reads `output`, possibly with the code wrapped in a function."""
    src = (ROOT / "zapier" / "decide.py").read_text(encoding="utf-8")
    form = {"judge_output": json.dumps(judged()), "name": "A B", "email": "x@y.z", "title": "T", "pass_threshold": "70"}
    ns = {"input_data": form}
    exec(src, ns)
    assert ns["output"]["decision"] == "advance"
    wrapped = "def run(input_data):\n" + textwrap.indent(src, "    ") + "\n    return output\n"
    ns = {}
    exec(wrapped, ns)
    assert ns["run"](form)["decision"] == "advance"
    ns = {}
    exec(src, ns)                                   # imported without input_data: defines functions only
    assert "output" not in ns


# ---- prompt ---------------------------------------------------------------------------------------------

def test_prompt_placeholders_are_all_filled():
    instructions, template = simulate.prompt_parts()
    assert "Return ONLY a JSON object" in instructions
    fields = {"today": "d", "title": "t", "requirements_block": "r", "name": "n", "resume_text": "x"}
    filled = simulate.fill(template, fields)
    assert "{{" not in filled
    with pytest.raises(KeyError):
        simulate.fill(template, {k: v for k, v in fields.items() if k != "resume_text"})


def test_recorded_results():
    """The recorded simulation runs agree with the expected decisions."""
    rows = json.loads((ROOT / "results" / "summary.json").read_text(encoding="utf-8"))
    expected = {("Alex Carter", "Software Engineer"): "advance", ("Alex Carter", "AI Engineer"): "reject",
                ("John W. Smith", "Software Engineer"): "reject", ("John W. Smith", "AI Engineer"): "reject"}
    assert len(rows) == 12
    assert all(expected[(r["name"], r["position"])] == r["decision"] for r in rows)


def test_timeline_note_goes_to_concerns_without_changing_decision():
    flagged = judged(timeline={"consistent": False, "note": "7+ years but graduated 2024"}, concerns=["other"])
    result = run_decide(json.dumps(flagged))
    assert result["decision"] == "advance" and result["timeline_flag"] is True
    assert result["concerns"].splitlines() == ["Timeline: 7+ years but graduated 2024", "other"]
    ok = run_decide(json.dumps(judged(timeline={"consistent": True, "note": ""})))
    assert ok["timeline_flag"] is False and ok["concerns"] == ""


def test_timeline_concern_not_duplicated():
    flagged = judged(timeline={"consistent": False, "note": "7+ years but graduated 2024"},
                     concerns=["Timeline: 7+ years claimed but degree in 2024"])
    result = run_decide(json.dumps(flagged))
    assert result["timeline_flag"] is True
    assert result["concerns"].splitlines() == ["Timeline: 7+ years claimed but degree in 2024"]


# ---- saving the evaluation (save_evaluation.py) ---------------------------------------------------------

import save_evaluation as se  # noqa: E402


def test_save_signature_matches_get_requirements():
    body = json.dumps({"TableName": "t", "Item": {"submission_id": {"S": "1"}}})
    args = ("AK", "SK", "us-east-1", "dynamodb.us-east-1.amazonaws.com", se.TARGET, body, NOW)
    assert se.sign(*args) == gr.sign(*args)          # the two pasted steps share one signer


def test_build_item_types():
    item = se.build_item({"aws_access_key": "AK", "aws_secret_key": "SK", "aws_region": "us-east-1",
                          "table": "t", "submission_id": 42, "name": "Alex Carter", "score": "100",
                          "llm_score": "98.5", "timeline_flag": "true", "mandatory_met": "False",
                          "concerns": "", "summary": "  ok  "})
    assert item == {"submission_id": {"S": "42"}, "name": {"S": "Alex Carter"}, "score": {"N": "100"},
                    "llm_score": {"N": "98.5"}, "timeline_flag": {"BOOL": True},
                    "mandatory_met": {"BOOL": False}, "summary": {"S": "ok"}}
    with pytest.raises(ValueError, match="submission_id"):
        se.build_item({"submission_id": " "})


def test_put_item_request():
    sent = {}

    def post(url, data, headers, timeout):
        sent.update(url=url, body=json.loads(data), headers=headers)
        return FakeResponse(200, {})

    out = se.put_item({"aws_access_key": "AK", "aws_secret_key": "SK", "aws_region": "us-west-2",
                       "table": "evals", "submission_id": "r1", "decision": "advance"}, NOW, post)
    assert out == {"saved": True, "table": "evals", "submission_id": "r1", "attributes": 2}
    assert sent["url"] == "https://dynamodb.us-west-2.amazonaws.com/"
    assert sent["headers"]["x-amz-target"] == "DynamoDB_20120810.PutItem"
    assert sent["body"] == {"TableName": "evals",
                            "Item": {"submission_id": {"S": "r1"}, "decision": {"S": "advance"}}}
    with pytest.raises(RuntimeError, match="400"):
        se.put_item({"aws_access_key": "AK", "aws_secret_key": "SK", "submission_id": "r1"}, NOW,
                    lambda *a, **k: FakeResponse(400, {"message": "bad"}))

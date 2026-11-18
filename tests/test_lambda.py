import base64
import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "lambda"))
sys.path.insert(0, str(ROOT / "zapier"))

import build_deploy  # noqa: E402
import handler  # noqa: E402

KEY = "test-key-123"
JOBS = json.loads((ROOT / "data" / "job_requirements.json").read_text(encoding="utf-8"))


class FakeTable:
    def __init__(self, key, items=()):
        self.key, self.items, self.scans = key, {i[key]: i for i in items}, 0

    def get_item(self, Key):
        item = self.items.get(Key[self.key])
        return {"Item": item} if item else {}

    def put_item(self, Item):
        self.items[Item[self.key]] = Item

    def scan(self, **kwargs):  # two pages, to exercise pagination
        self.scans += 1
        items = list(self.items.values())
        half = len(items) // 2
        if "ExclusiveStartKey" in kwargs:
            return {"Items": items[half:]}
        return {"Items": items[:half], "LastEvaluatedKey": {"k": 1}}


def as_dynamodb(job):  # boto3 returns numbers as Decimal
    return {k: Decimal(str(v)) if isinstance(v, (int, float)) else v for k, v in job.items()}


@pytest.fixture
def tables(monkeypatch):
    monkeypatch.setenv("API_KEY", KEY)
    t = {"smarthire_job_requirements": FakeTable("position", [as_dynamodb(j) for j in JOBS]),
         "smarthire_evaluations": FakeTable("submission_id")}
    monkeypatch.setattr(handler, "table", lambda name: t[name])
    return t


def event(method, path, query=None, body=None, key=KEY, content_type="application/json", b64=False):
    headers = {"Content-Type": content_type}
    if key is not None:
        headers["X-Api-Key"] = key
    if body is not None and b64:
        body = base64.b64encode(body.encode()).decode()
    return {"version": "2.0", "rawPath": path, "queryStringParameters": query, "headers": headers,
            "body": body, "isBase64Encoded": b64,
            "requestContext": {"http": {"method": method}, "stage": "$default"}}


def call(*args, **kwargs):
    r = handler.lambda_handler(event(*args, **kwargs))
    return r["statusCode"], json.loads(r["body"])


def test_requirements_by_title(tables):
    status, body = call("GET", "/requirements", {"position": "Software Engineer"})
    assert status == 200
    assert body["title"] == "Software Engineer" and body["pass_threshold"] == 70 and body["min_years"] == 3
    assert body["requirements_block"].startswith("1. [MANDATORY] 3+ years of relevant experience\n2. ")


def test_requirements_match_the_zapier_code_step(tables):
    import get_requirements as gr  # the 0-9 Code step: the Webhooks step must output the same fields
    for job in JOBS:
        _, body = call("GET", "/requirements", {"position": job["title"]})
        assert body == gr.to_output(job)


def test_auth(tables):
    assert call("GET", "/requirements", {"position": "AI Engineer"}, key=None)[0] == 401
    assert call("GET", "/requirements", {"position": "AI Engineer"}, key="wrong")[0] == 401


def test_no_api_key_configured_rejects_everything(tables, monkeypatch):
    monkeypatch.setenv("API_KEY", "")
    assert call("GET", "/requirements", {"position": "AI Engineer"}, key="")[0] == 401


def test_requirements_errors(tables):
    assert call("GET", "/requirements")[0] == 400
    status, body = call("GET", "/requirements", {"position": "Chef"})
    assert status == 404 and "chef" in body["error"]
    assert call("DELETE", "/requirements")[0] == 404
    assert call("GET", "/nope")[0] == 404


def test_save_evaluation_json(tables):
    status, body = call("POST", "/evaluations", body=json.dumps({
        "submission_id": "zap-1", "name": "Alex Carter", "position": "Software Engineer",
        "decision": "advance", "score": "100", "llm_score": "92.5", "timeline_flag": "true", "concerns": ""}))
    assert status == 200 and body["saved"] is True
    item = tables["smarthire_evaluations"].items["zap-1"]
    assert item["score"] == Decimal("100") and item["llm_score"] == Decimal("92.5")
    assert item["timeline_flag"] is True and "concerns" not in item
    assert item["position_key"] == "software_engineer"


def test_save_evaluation_form_encoded_and_base64(tables):
    status, _ = call("POST", "/evaluations", body="submission_id=zap-2&name=John+Smith&score=17",
                     content_type="application/x-www-form-urlencoded", b64=True)
    assert status == 200
    assert tables["smarthire_evaluations"].items["zap-2"]["name"] == "John Smith"


def test_save_evaluation_errors(tables):
    assert call("POST", "/evaluations", body=json.dumps({"name": "x"}))[0] == 400
    assert call("POST", "/evaluations", body="{not json")[0] == 400
    assert call("POST", "/evaluations", body="[1, 2]")[0] == 400


def test_rankings(tables):
    for sid, name, pos, score in [("1", "Alex", "Software Engineer", "100"), ("2", "John", "Software Engineer", "17"),
                                  ("3", "Alex", "AI Engineer", "44"), ("4", "Bo", "Software Engineer", "88")]:
        call("POST", "/evaluations", body=json.dumps(
            {"submission_id": sid, "name": name, "position": pos, "score": score, "decision": "x"}))
    status, body = call("GET", "/rankings", {"position": "software_engineer"})
    assert status == 200 and body["count"] == 3
    assert [(c["rank"], c["name"], c["score"]) for c in body["candidates"]] == [(1, "Alex", 100), (2, "Bo", 88), (3, "John", 17)]
    assert call("GET", "/rankings")[1]["count"] == 4


def test_rest_api_event_with_stage_prefix(tables):
    r = handler.lambda_handler({"httpMethod": "GET", "path": "/prod/requirements/",
                                "requestContext": {"stage": "prod"}, "headers": {"x-api-key": KEY},
                                "queryStringParameters": {"position": "ai engineer"}})
    assert r["statusCode"] == 200 and json.loads(r["body"])["title"] == "AI Engineer"


def test_unexpected_error_is_500(tables, monkeypatch):
    def boom(name):
        raise RuntimeError("AccessDenied")
    monkeypatch.setattr(handler, "table", boom)
    assert call("GET", "/requirements", {"position": "AI Engineer"}) == (500, {"error": "RuntimeError"})


def test_deploy_script_embeds_current_handler():
    script = build_deploy.script()
    assert (ROOT / "lambda" / "handler.py").read_text(encoding="utf-8") in script
    assert not any(line.strip().startswith("set -e") for line in script.splitlines())
    assert (ROOT / "lambda" / "deploy.sh").read_text(encoding="utf-8") == script, "run lambda/build_deploy.py"


def test_role_policy_is_least_privilege():
    statements = build_deploy.role_policy()["Statement"]
    actions = sorted(a for s in statements for a in s["Action"] if a.startswith("dynamodb:"))
    assert actions == ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Scan"]


@pytest.mark.skipif(subprocess.run(["bash", "-c", "true"], capture_output=True).returncode != 0, reason="no bash")
def test_deploy_script_is_valid_bash():
    r = subprocess.run(["bash", "-n"], input=(ROOT / "lambda" / "deploy.sh").read_bytes(),
                       capture_output=True)
    assert r.returncode == 0, r.stderr

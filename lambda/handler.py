"""SmartHire AI API - AWS Lambda behind an API Gateway HTTP API.

Zapier calls this with Webhooks by Zapier instead of signing DynamoDB requests itself, so no AWS
credentials live in the Zap: DynamoDB is only reachable through this function's IAM role.

Routes (every request needs the header  x-api-key: <API_KEY>):
    GET  /requirements?position=Software Engineer   job requirements, flattened for Zapier
    POST /evaluations                               save one evaluation (JSON or form body)
    GET  /rankings?position=software_engineer       evaluated candidates for a position, best first

Environment: API_KEY, REQUIREMENTS_TABLE (smarthire_job_requirements),
             EVALUATIONS_TABLE (smarthire_evaluations)
"""
import base64
import hmac
import json
import os
import re
from decimal import Decimal
from urllib.parse import parse_qsl

_TABLES = {}


def table(name):
    """A boto3 Table, created once per container. Tests replace this function."""
    if name not in _TABLES:
        import boto3  # in the Lambda runtime; not needed to run the tests
        _TABLES[name] = boto3.resource("dynamodb").Table(name)
    return _TABLES[name]


def position_key(position):
    """'Software Engineer' -> 'software_engineer', the requirements table's partition key."""
    return re.sub(r"[^a-z0-9]+", "_", (position or "").strip().lower()).strip("_")


def plain(value):
    """DynamoDB values from boto3 (Decimal, sets) -> JSON-friendly Python."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    return value


def stored(value):
    """A webhook field (usually text) -> what to store: number, bool, string, or None to skip."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if text == "":
        return None
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return Decimal(text)
    return text


def requirements_output(job):
    """Same fields as zapier/get_requirements.py, so the later Zap steps need no changes."""
    mandatory, others = job.get("mandatory", []), job.get("requirements", [])
    lines = [f"{i}. [MANDATORY] {r}" for i, r in enumerate(mandatory, 1)]
    lines += [f"{i}. {r}" for i, r in enumerate(others, len(mandatory) + 1)]
    return {
        "position": job["position"],
        "title": job.get("title", job["position"]),
        "min_years": job.get("min_years", 0),
        "pass_threshold": job.get("pass_threshold", 70),
        "mandatory": "\n".join(mandatory),
        "requirements": "\n".join(others),
        "requirements_block": "\n".join(lines),
    }


def response(status, body):
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(body, ensure_ascii=False)}


def request_parts(event):
    """(method, path, query, headers, body) for HTTP API (payload 2.0) and REST API (1.0) events."""
    http = event.get("requestContext", {}).get("http", {})
    method = (http.get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("rawPath") or event.get("path") or "/"
    stage = event.get("requestContext", {}).get("stage")
    if stage and stage != "$default" and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1:]
    query = event.get("queryStringParameters") or {}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return method, path.rstrip("/") or "/", query, headers, body


def parse_body(body, content_type):
    if not body.strip():
        return {}
    if "application/x-www-form-urlencoded" in (content_type or ""):
        return dict(parse_qsl(body, keep_blank_values=True))
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("body must be a JSON object")
    return data


def get_requirements(query):
    key = position_key(query.get("position"))
    if not key:
        return response(400, {"error": "query parameter 'position' is required"})
    item = table(os.environ.get("REQUIREMENTS_TABLE", "smarthire_job_requirements")).get_item(
        Key={"position": key}).get("Item")
    if not item:
        return response(404, {"error": f"no job requirements for position '{key}'"})
    return response(200, requirements_output(plain(item)))


def save_evaluation(data):
    submission_id = str(data.get("submission_id") or "").strip()
    if not submission_id:
        return response(400, {"error": "'submission_id' is required (the table's partition key)"})
    item = {k: v for k, v in ((k, stored(v)) for k, v in data.items()) if v is not None}
    item["submission_id"] = submission_id
    if "position" in item:
        item["position_key"] = position_key(str(item["position"]))
    name = os.environ.get("EVALUATIONS_TABLE", "smarthire_evaluations")
    table(name).put_item(Item=item)
    return response(200, {"saved": True, "table": name, "submission_id": submission_id,
                          "attributes": len(item)})


def rankings(query):
    key = position_key(query.get("position"))
    tbl = table(os.environ.get("EVALUATIONS_TABLE", "smarthire_evaluations"))
    items, kwargs = [], {}
    while True:  # a small table: a paginated Scan is fine
        page = tbl.scan(**kwargs)
        items += [plain(i) for i in page.get("Items", [])]
        if "LastEvaluatedKey" not in page:
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    if key:
        items = [i for i in items if (i.get("position_key") or position_key(str(i.get("position", "")))) == key]
    scored = [i for i in items if isinstance(i.get("score"), (int, float))]
    scored.sort(key=lambda i: (-i["score"], str(i.get("evaluated_at", ""))))
    ranked = [{"rank": n, "name": i.get("name", ""), "position": i.get("position", ""),
               "score": i["score"], "decision": i.get("decision", ""),
               "submission_id": i["submission_id"], "evaluated_at": i.get("evaluated_at", "")}
              for n, i in enumerate(scored, 1)]
    return response(200, {"position": key or "all", "count": len(ranked), "candidates": ranked})


def authorized(headers):
    expected = os.environ.get("API_KEY", "")
    given = headers.get("x-api-key", "")
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def lambda_handler(event, context=None):
    try:
        method, path, query, headers, body = request_parts(event)
        if not authorized(headers):
            return response(401, {"error": "missing or wrong x-api-key"})
        if method == "GET" and path == "/requirements":
            return get_requirements(query)
        if method == "POST" and path == "/evaluations":
            try:
                data = parse_body(body, headers.get("content-type"))
            except ValueError as e:  # json.JSONDecodeError is a ValueError
                return response(400, {"error": f"invalid body: {e}"})
            return save_evaluation(data)
        if method == "GET" and path == "/rankings":
            return rankings(query)
        return response(404, {"error": f"no route {method} {path}"})
    except Exception as e:  # keep the reason visible in Zapier's test output
        print(f"error: {e!r}")
        return response(500, {"error": type(e).__name__})

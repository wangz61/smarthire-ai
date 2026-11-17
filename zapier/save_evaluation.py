"""Code by Zapier (Python) step: save the evaluation to Amazon DynamoDB.

Zapier no longer lists an Amazon DynamoDB app, so like get_requirements.py this step calls the
DynamoDB API directly (PutItem), signed with AWS Signature Version 4, using only the standard
library and `requests`. It is self-contained, so it can be pasted into a Code step as is.

Input Data (set these in the Zapier step):
    aws_access_key, aws_secret_key, aws_region   same IAM user as the requirements step
    table            e.g. smarthire_evaluations (partition key: submission_id)
    submission_id    a unique id for the application, e.g. the form's Response ID or {{zap_meta_id}}
    every other field is stored as an attribute: name, email, position, decision, score, llm_score,
    timeline_flag, summary, concerns, evaluated_at, evaluation_json, ...

Numbers ("100", "98.5") are stored as DynamoDB numbers, "true"/"false" as booleans, everything
else as strings. Empty values are skipped.

Output: saved ("true"), table, submission_id, attributes (how many were written).
"""
import datetime
import hashlib
import hmac
import json
import re

import requests

SERVICE = "dynamodb"
TARGET = "DynamoDB_20120810.PutItem"
CONNECTION_FIELDS = {"aws_access_key", "aws_secret_key", "aws_region", "table"}


def _hmac(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sign(access_key, secret_key, region, host, target, body, now):
    """Headers for a SigV4-signed DynamoDB JSON request (POST /). Same as in get_requirements.py."""
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    headers = {
        "content-type": "application/x-amz-json-1.0",
        "host": host,
        "x-amz-date": amz_date,
        "x-amz-target": target,
    }
    signed = ";".join(sorted(headers))
    canonical = "\n".join([
        "POST", "/", "",
        "".join(f"{k}:{headers[k]}\n" for k in sorted(headers)),
        signed,
        hashlib.sha256(body.encode("utf-8")).hexdigest(),
    ])
    scope = f"{date}/{region}/{SERVICE}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope,
                         hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(("AWS4" + secret_key).encode("utf-8"), date), region), SERVICE), "aws4_request")
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    headers["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                                f"SignedHeaders={signed}, Signature={signature}")
    return headers


def attribute(value):
    """A Zapier field value (always text) -> DynamoDB attribute value, or None to skip it."""
    if value is None:
        return None
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, float)):
        return {"N": str(value)}
    text = str(value).strip()
    if text == "":
        return None
    if text.lower() in ("true", "false"):
        return {"BOOL": text.lower() == "true"}
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return {"N": text}
    return {"S": text}


def build_item(data):
    if not str(data.get("submission_id") or "").strip():
        raise ValueError("submission_id is required (it is the table's partition key)")
    item = {}
    for key, value in data.items():
        if key in CONNECTION_FIELDS:
            continue
        av = attribute(value)
        if av is not None:
            item[key] = av
    item["submission_id"] = {"S": str(data["submission_id"]).strip()}  # the key is always a string
    return item


def put_item(data, now=None, post=None):
    region = data.get("aws_region") or "us-east-1"
    table = data.get("table") or "smarthire_evaluations"
    host = f"dynamodb.{region}.amazonaws.com"
    item = build_item(data)
    body = json.dumps({"TableName": table, "Item": item})
    headers = sign(data["aws_access_key"], data["aws_secret_key"], region, host, TARGET, body,
                   now or datetime.datetime.now(datetime.timezone.utc))
    response = (post or requests.post)(f"https://{host}/", data=body, headers=headers, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"DynamoDB PutItem failed ({response.status_code}): {response.text[:300]}")
    return {"saved": True, "table": table, "submission_id": item["submission_id"]["S"], "attributes": len(item)}


def main(data):
    return put_item(data)


# Read-only lookup: works whether Zapier runs this at module level or inside a function.
_zapier_input = globals().get("input_data") or locals().get("input_data")
if _zapier_input is not None:
    output = main(_zapier_input)

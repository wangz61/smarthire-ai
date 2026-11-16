"""Code by Zapier (Python) step: read one job's requirements from Amazon DynamoDB.

Zapier's DynamoDB app can create items but cannot read them, so this step calls the DynamoDB
GetItem API directly, signed with AWS Signature Version 4. Only the standard library and
`requests` are used, which is all a Code by Zapier step is guaranteed to have.

Input Data (set these in the Zapier step):
    position        the "Position" answer from the form, e.g. "Software Engineer"
    aws_access_key  access key of the IAM user that may read the table
    aws_secret_key  its secret key
    aws_region      e.g. us-east-1
    table           e.g. smarthire_job_requirements

Output: title, min_years, pass_threshold, mandatory, requirements (one per line), and
requirements_block, a numbered list ready to paste into the judge prompt.
"""
import datetime
import hashlib
import hmac
import json
import re

import requests

SERVICE = "dynamodb"
TARGET = "DynamoDB_20120810.GetItem"


def position_key(position):
    """'Software Engineer' -> 'software_engineer', the table's partition key."""
    return re.sub(r"[^a-z0-9]+", "_", position.strip().lower()).strip("_")


def _hmac(key, msg):
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sign(access_key, secret_key, region, host, target, body, now):
    """Headers for a SigV4-signed DynamoDB JSON request (POST /)."""
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


def unmarshal(value):
    """DynamoDB attribute value ({"S": "x"}, {"N": "3"}, {"L": [...]}, ...) -> plain Python."""
    (kind, v), = value.items()
    if kind == "S":
        return v
    if kind == "N":
        return int(v) if re.fullmatch(r"-?\d+", v) else float(v)
    if kind == "BOOL":
        return v
    if kind == "NULL":
        return None
    if kind == "L":
        return [unmarshal(x) for x in v]
    if kind == "M":
        return {k: unmarshal(x) for k, x in v.items()}
    if kind in ("SS", "NS"):
        return [unmarshal({kind[0]: x}) for x in v]
    raise ValueError(f"unsupported DynamoDB type {kind}")


def get_item(position, access_key, secret_key, region, table, now=None, post=None):
    host = f"dynamodb.{region}.amazonaws.com"
    body = json.dumps({"TableName": table, "Key": {"position": {"S": position_key(position)}}})
    headers = sign(access_key, secret_key, region, host, TARGET, body,
                   now or datetime.datetime.now(datetime.timezone.utc))
    response = (post or requests.post)(f"https://{host}/", data=body, headers=headers, timeout=10)
    if response.status_code != 200:
        raise RuntimeError(f"DynamoDB GetItem failed ({response.status_code}): {response.text[:300]}")
    item = response.json().get("Item")
    if not item:
        raise LookupError(f"no job requirements for position {position_key(position)!r} in {table}")
    return {k: unmarshal(v) for k, v in item.items()}


def to_output(job):
    """Flatten an item into strings, since Zapier passes step fields on as text."""
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


def main(data):
    job = get_item(data["position"], data["aws_access_key"], data["aws_secret_key"],
                   data.get("aws_region") or "us-east-1", data.get("table") or "smarthire_job_requirements")
    return to_output(job)


# In Zapier, `input_data` is provided and `output` is read back. Locally, import main() instead.
# Read-only lookup: works whether Zapier runs this at module level or inside a function.
_zapier_input = globals().get("input_data") or locals().get("input_data")
if _zapier_input is not None:
    output = main(_zapier_input)

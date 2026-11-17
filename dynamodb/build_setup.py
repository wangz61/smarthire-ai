"""Generate the DynamoDB setup files from data/job_requirements.json.

    setup.sh          paste into AWS CloudShell: creates both tables and writes the job requirements
    items/*.json      each job as a DynamoDB-JSON item (also usable in the console's "JSON view")
    iam_policy.json   least-privilege policy for the IAM user that Zapier uses
    iam.sh            paste into AWS CloudShell: creates that IAM user and prints its access key
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
JOBS = json.loads((HERE.parent / "data" / "job_requirements.json").read_text(encoding="utf-8"))
REQUIREMENTS_TABLE = "smarthire_job_requirements"
EVALUATIONS_TABLE = "smarthire_evaluations"


def marshal(value):
    """Plain Python -> DynamoDB attribute value (the inverse of get_requirements.unmarshal)."""
    if isinstance(value, bool):
        return {"BOOL": value}
    if isinstance(value, (int, float)):
        return {"N": str(value)}
    if isinstance(value, str):
        return {"S": value}
    if isinstance(value, list):
        return {"L": [marshal(v) for v in value]}
    if isinstance(value, dict):
        return {"M": {k: marshal(v) for k, v in value.items()}}
    if value is None:
        return {"NULL": True}
    raise TypeError(type(value))


def item(job):
    return {k: marshal(v) for k, v in job.items()}


def setup_script():
    # Meant to be pasted into an interactive CloudShell, so no `set -e` (an error would close the
    # session), and every step is safe to run again.
    lines = [
        "#!/usr/bin/env bash",
        "# SmartHire AI - DynamoDB setup. Paste into AWS CloudShell (in the region you will use).",
        "# Safe to run more than once.",
        "",
    ]
    for table, key in ((REQUIREMENTS_TABLE, "position"), (EVALUATIONS_TABLE, "submission_id")):
        lines += [
            f"if aws dynamodb describe-table --table-name {table} >/dev/null 2>&1; then",
            f"  echo \"table {table} already exists\"",
            "else",
            f"  aws dynamodb create-table --table-name {table} \\",
            f"    --attribute-definitions AttributeName={key},AttributeType=S \\",
            f"    --key-schema AttributeName={key},KeyType=HASH \\",
            "    --billing-mode PAY_PER_REQUEST --query TableDescription.TableStatus --output text",
            "fi",
            f"echo \"waiting for {table} to become ACTIVE (up to ~20 s)...\"",
            f"aws dynamodb wait table-exists --table-name {table} && echo \"{table} is ready\"",
            "",
        ]
    for job in JOBS:
        lines += [
            # "Bachelor's" contains a quote, so close, escape and reopen the single-quoted argument.
            f"aws dynamodb put-item --table-name {REQUIREMENTS_TABLE} --item '"
            + json.dumps(item(job)).replace("'", "'\"'\"'") + "' && echo \"wrote " + job["position"] + "\"",
        ]
    lines += [
        "",
        f"aws dynamodb scan --table-name {REQUIREMENTS_TABLE} \\",
        "  --query 'Items[].{position: position.S, title: title.S, threshold: pass_threshold.N}' --output table",
        "",
    ]
    return "\n".join(lines)


def iam_policy():
    arn = "arn:aws:dynamodb:*:*:table/{}"
    return {
        "Version": "2012-10-17",
        "Statement": [
            {"Sid": "ReadJobRequirements", "Effect": "Allow", "Action": ["dynamodb:GetItem"],
             "Resource": arn.format(REQUIREMENTS_TABLE)},
            {"Sid": "WriteEvaluations", "Effect": "Allow",
             "Action": ["dynamodb:PutItem", "dynamodb:DescribeTable"],
             "Resource": arn.format(EVALUATIONS_TABLE)},
            {"Sid": "ZapierTableDropdown", "Effect": "Allow", "Action": ["dynamodb:ListTables"], "Resource": "*"},
        ],
    }


def iam_script(user="smarthire-zapier"):
    policy = json.dumps(iam_policy())
    return "\n".join([
        "#!/usr/bin/env bash",
        "# SmartHire AI - IAM user for Zapier. Paste into AWS CloudShell. No `set -e`: errors are printed,",
        "# and the session stays open.",
        f"aws iam get-user --user-name {user} >/dev/null 2>&1 || aws iam create-user --user-name {user} >/dev/null",
        f"aws iam put-user-policy --user-name {user} --policy-name smarthire-dynamodb --policy-document '{policy}' \\",
        "  && echo 'policy attached'",
        "echo 'Access key ID and secret access key (shown only once, keep them private):'",
        f"aws iam create-access-key --user-name {user} --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text",
        "",
    ])


if __name__ == "__main__":
    (HERE / "items").mkdir(exist_ok=True)
    for job in JOBS:
        (HERE / "items" / f"{job['position']}.json").write_text(json.dumps(item(job), indent=2) + "\n", encoding="utf-8")
    (HERE / "setup.sh").write_text(setup_script(), encoding="utf-8", newline="\n")
    (HERE / "iam_policy.json").write_text(json.dumps(iam_policy(), indent=2) + "\n", encoding="utf-8")
    (HERE / "iam.sh").write_text(iam_script(), encoding="utf-8", newline="\n")
    print("wrote setup.sh, iam.sh, iam_policy.json and", len(JOBS), "items")

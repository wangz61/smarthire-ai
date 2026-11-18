"""Generate lambda/deploy.sh: paste it into AWS CloudShell to deploy the SmartHire API.

The script embeds handler.py, so CloudShell needs no upload. It is safe to run again: it updates the
code of an existing function and keeps its API key.

    python lambda/build_deploy.py
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
FUNCTION, ROLE, API = "smarthire-api", "smarthire-lambda-role", "smarthire-api"
REQUIREMENTS_TABLE, EVALUATIONS_TABLE = "smarthire_job_requirements", "smarthire_evaluations"

TRUST = {"Version": "2012-10-17", "Statement": [
    {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]}


def role_policy():
    arn = "arn:aws:dynamodb:*:*:table/{}"
    return {"Version": "2012-10-17", "Statement": [
        {"Sid": "ReadRequirements", "Effect": "Allow", "Action": ["dynamodb:GetItem"],
         "Resource": arn.format(REQUIREMENTS_TABLE)},
        {"Sid": "WriteAndRankEvaluations", "Effect": "Allow", "Action": ["dynamodb:PutItem", "dynamodb:Scan"],
         "Resource": arn.format(EVALUATIONS_TABLE)},
        {"Sid": "Logs", "Effect": "Allow",
         "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "*"},
    ]}


def script():
    handler = (HERE / "handler.py").read_text(encoding="utf-8")
    assert "\nPY\n" not in handler
    return f"""#!/usr/bin/env bash
# SmartHire AI - deploy API Gateway (HTTP API) + Lambda. Paste into AWS CloudShell (same region as the tables).
# Safe to run more than once. No `set -e`, so an error does not close the CloudShell session.
REGION=$(aws configure get region); REGION=${{REGION:-$AWS_REGION}}; REGION=${{REGION:-us-east-1}}
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "account $ACCOUNT, region $REGION"
mkdir -p ~/smarthire-api && cd ~/smarthire-api

# 1. IAM role for the function (least privilege)
cat > trust.json <<'JSON'
{json.dumps(TRUST, indent=2)}
JSON
cat > policy.json <<'JSON'
{json.dumps(role_policy(), indent=2)}
JSON
if ! aws iam get-role --role-name {ROLE} >/dev/null 2>&1; then
  aws iam create-role --role-name {ROLE} --assume-role-policy-document file://trust.json \\
    --query Role.Arn --output text
  NEW_ROLE=1
fi
aws iam put-role-policy --role-name {ROLE} --policy-name smarthire-dynamodb --policy-document file://policy.json
ROLE_ARN=$(aws iam get-role --role-name {ROLE} --query Role.Arn --output text)
echo "role $ROLE_ARN"
[ -n "$NEW_ROLE" ] && echo "waiting 15 s for the new role to propagate..." && sleep 15

# 2. Lambda function
cat > handler.py <<'PY'
{handler}PY
rm -f function.zip && python3 -m zipfile -c function.zip handler.py
if aws lambda get-function --function-name {FUNCTION} >/dev/null 2>&1; then
  API_KEY=$(aws lambda get-function-configuration --function-name {FUNCTION} \\
    --query Environment.Variables.API_KEY --output text)
  aws lambda update-function-code --function-name {FUNCTION} --zip-file fileb://function.zip \\
    --query LastModified --output text
  aws lambda wait function-updated --function-name {FUNCTION}
else
  API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(24))")
  for attempt in 1 2 3 4 5 6; do
    aws lambda create-function --function-name {FUNCTION} --runtime python3.12 \\
      --handler handler.lambda_handler --role "$ROLE_ARN" --zip-file fileb://function.zip \\
      --timeout 10 --memory-size 256 \\
      --environment "Variables={{API_KEY=$API_KEY,REQUIREMENTS_TABLE={REQUIREMENTS_TABLE},EVALUATIONS_TABLE={EVALUATIONS_TABLE}}}" \\
      --query FunctionArn --output text && break
    echo "role not ready yet, retrying in 10 s ($attempt/6)"; sleep 10
  done
  aws lambda wait function-active --function-name {FUNCTION}
fi
FUNCTION_ARN=$(aws lambda get-function --function-name {FUNCTION} --query Configuration.FunctionArn --output text)

# 3. API Gateway HTTP API: quick create, every route goes to the function
API_ID=$(aws apigatewayv2 get-apis --query "Items[?Name=='{API}'].ApiId | [0]" --output text)
if [ -z "$API_ID" ] || [ "$API_ID" = "None" ]; then
  API_ID=$(aws apigatewayv2 create-api --name {API} --protocol-type HTTP --target "$FUNCTION_ARN" \\
    --query ApiId --output text)
fi
aws lambda add-permission --function-name {FUNCTION} --statement-id apigateway-invoke \\
  --action lambda:InvokeFunction --principal apigateway.amazonaws.com \\
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT:$API_ID/*" >/dev/null 2>&1
URL="https://$API_ID.execute-api.$REGION.amazonaws.com"

# 4. Smoke test
echo; echo "--- GET /requirements without a key (expect 401)"
curl -s -o /dev/null -w "%{{http_code}}\\n" "$URL/requirements?position=Software%20Engineer"
echo "--- GET /requirements?position=Software Engineer"
curl -s -H "x-api-key: $API_KEY" "$URL/requirements?position=Software%20Engineer"; echo
echo
echo "=============================================================="
echo " API base URL : $URL"
echo " x-api-key    : $API_KEY"
echo " Put both into the Zapier Webhooks steps. Do not share the key."
echo "=============================================================="
"""


if __name__ == "__main__":
    (HERE / "deploy.sh").write_text(script(), encoding="utf-8", newline="\n")
    print("wrote", HERE / "deploy.sh")

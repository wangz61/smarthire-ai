#!/usr/bin/env bash
# SmartHire AI - IAM user for Zapier. Paste into AWS CloudShell.
set -euo pipefail
aws iam create-user --user-name smarthire-zapier >/dev/null
aws iam put-user-policy --user-name smarthire-zapier --policy-name smarthire-dynamodb --policy-document '{"Version": "2012-10-17", "Statement": [{"Sid": "ReadJobRequirements", "Effect": "Allow", "Action": ["dynamodb:GetItem"], "Resource": "arn:aws:dynamodb:*:*:table/smarthire_job_requirements"}, {"Sid": "WriteEvaluations", "Effect": "Allow", "Action": ["dynamodb:PutItem", "dynamodb:DescribeTable"], "Resource": "arn:aws:dynamodb:*:*:table/smarthire_evaluations"}, {"Sid": "ZapierTableDropdown", "Effect": "Allow", "Action": ["dynamodb:ListTables"], "Resource": "*"}]}'
echo 'Access key ID and secret access key (shown only once, keep them private):'
aws iam create-access-key --user-name smarthire-zapier --query 'AccessKey.[AccessKeyId,SecretAccessKey]' --output text

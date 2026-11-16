#!/usr/bin/env bash
# SmartHire AI - DynamoDB setup. Paste into AWS CloudShell (in the region you will use).
set -euo pipefail

aws dynamodb create-table --table-name smarthire_job_requirements \
  --attribute-definitions AttributeName=position,AttributeType=S \
  --key-schema AttributeName=position,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST >/dev/null 2>&1 || echo "table smarthire_job_requirements already exists"
aws dynamodb wait table-exists --table-name smarthire_job_requirements

aws dynamodb create-table --table-name smarthire_evaluations \
  --attribute-definitions AttributeName=submission_id,AttributeType=S \
  --key-schema AttributeName=submission_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST >/dev/null 2>&1 || echo "table smarthire_evaluations already exists"
aws dynamodb wait table-exists --table-name smarthire_evaluations

aws dynamodb put-item --table-name smarthire_job_requirements --item '{"position": {"S": "software_engineer"}, "title": {"S": "Software Engineer"}, "min_years": {"N": "3"}, "mandatory": {"L": [{"S": "3+ years of relevant experience"}]}, "requirements": {"L": [{"S": "Bachelor'"'"'s degree in Computer Science or related field"}, {"S": "Proficiency in Python, JavaScript, or similar languages"}, {"S": "Experience with SQL and databases"}, {"S": "Familiarity with cloud platforms (AWS/GCP/Azure)"}, {"S": "Experience with Git / version control"}, {"S": "Strong communication skills"}]}, "pass_threshold": {"N": "70"}}'
aws dynamodb put-item --table-name smarthire_job_requirements --item '{"position": {"S": "ai_engineer"}, "title": {"S": "AI Engineer"}, "min_years": {"N": "3"}, "mandatory": {"L": [{"S": "3+ years of experience in AI/ML engineering"}]}, "requirements": {"L": [{"S": "Bachelor'"'"'s or Master'"'"'s degree in CS, AI, or related field"}, {"S": "Proficiency in Python and ML frameworks (TensorFlow, PyTorch, etc.)"}, {"S": "Experience with LLMs, prompt engineering, or model fine-tuning"}, {"S": "Familiarity with MLOps and deployment pipelines"}, {"S": "Experience with cloud platforms (AWS SageMaker, GCP Vertex AI, etc.)"}, {"S": "Strong understanding of data preprocessing and feature engineering"}, {"S": "Experience with Git / version control"}, {"S": "Strong communication skills"}]}, "pass_threshold": {"N": "70"}}'

aws dynamodb scan --table-name smarthire_job_requirements \
  --query 'Items[].{position: position.S, title: title.S, threshold: pass_threshold.N}' --output table

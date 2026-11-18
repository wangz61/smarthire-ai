# Resume project entry (Module 3)

**SmartHire AI – Automated Resume Screening & Candidate Ranking Pipeline**
*Technologies: Zapier (Webhooks, Paths, Formatter, Code), AWS Lambda, API Gateway, DynamoDB, IAM, OpenAI GPT-4o, Python, pytest*

- Designed and built an end-to-end resume screening pipeline with Zapier as the no-code orchestration layer: Google Forms intake → resume text extraction → LLM evaluation → advance/reject email, with no manual triage.
- Exposed job requirements and evaluation storage as a serverless REST API (API Gateway HTTP API → Python Lambda → DynamoDB) called through Zapier Webhooks (GET/POST), so evaluation criteria are configured per role without redeploying the workflow and no AWS credentials live in Zapier.
- Secured the API with a shared-key header checked in constant time, and gave the Lambda a least-privilege IAM role (GetItem on requirements; PutItem/Scan on evaluations), deployed with an idempotent one-paste CloudShell script.
- Used OpenAI as an LLM judge that grades each requirement as met/partial/not met with resume evidence and returns strict JSON; kept the final advance/reject decision in deterministic code (mandatory requirements + 70-point threshold), routing malformed judge output to human review.
- Found and fixed a judge failure on real Zapier input (experience overlapping a degree was miscounted, rejecting a qualified candidate 3/3 runs) with a timeline-consistency rule; verified 12/12 expected decisions and 3/3 rejection of a prompt-injection resume.
- Added a `/rankings` endpoint that ranks evaluated candidates per role by score, and covered the API, decision rules, and AWS SigV4 signing with 45 pytest tests.

---

## 说明（为什么和课件示例不完全一样）

课件示例里写的是「Formatter 规范化简历文本」「AI by Zapier (GPT5.5)」「advance 用 Email by Zapier、reject 用 Gmail」。简历描述要和实际做的一致，面试时才经得起追问。所以这里按我们的实现写：

- 文本提取用的是 Files by Zapier（Formatter 只用来从上传链接提取文件 ID）。
- 评委模型：Zap 中实际运行的是 gpt-4o（ChatGPT/OpenAI 应用），本地模拟用的是 gpt-4.1。
- 两种邮件都通过 Gmail 发送。

如果你把 Zap 改成了课件的做法，把相应的词换掉即可。

面试时值得展开讲的几点：
1. 为什么决策放在代码里，而不是让 LLM 直接决定（可审计，不会被简历里的注入文本左右）。
2. 时间线问题是怎么发现的：在 Zapier 的真实输入上，同一份简历连续 3 次被拒，排查后定位到在读期间的工作经历没有被计入。
3. 为什么要用 API Gateway + Lambda，而不是在 Zap 里直接放 AWS 密钥（密钥泄露的影响范围、最小权限）。

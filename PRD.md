# PRD · Homework 0-9 SmartHire AI：简历筛选与候选人评估

## 1. 目标
在 Zapier 中搭建一条端到端的简历筛选流程：候选人通过 Google Forms 投递简历 → 提取简历文本 → 从 Amazon DynamoDB 读取岗位要求 → 用 OpenAI 作为评委（LLM judge）按岗位要求评分 → 生成结构化的评分和决定（advance / reject） → 自动发送通过或拒绝邮件。

## 2. 需求

| ID | 优先级 | 需求 |
| --- | --- | --- |
| F-1 | P0 | Google Form：姓名、邮箱、申请岗位（Software Engineer / AI Engineer 下拉）、简历文件上传（.docx / .pdf） |
| F-2 | P0 | Zapier 触发器：Google Forms「New Form Response」 |
| X-1 | P0 | 提取简历文本：Google Drive 取到上传的文件 → Files by Zapier「Text From File」 |
| D-1 | P0 | DynamoDB 表 `smarthire_job_requirements`，分区键 `position`；写入作业给的两个岗位（必备条件、加分项、通过阈值） |
| D-2 | P0 | Zap 中读取岗位要求。Zapier 的 DynamoDB 集成只有写入（Create Item）和新条目触发，没有读取动作，所以用 Code by Zapier（Python，仅标准库 + requests）以 SigV4 签名调用 DynamoDB `GetItem` |
| D-3 | P1 | 评估结果用 Zapier 的 DynamoDB「Create Item」写入 `smarthire_evaluations`，便于追踪 |
| J-1 | P0 | 评委提示词：逐条判断每项要求 met / partial / not_met 并给证据；单独判断必备条件；给出 0–100 总分和建议；只输出 JSON |
| J-2 | P0 | 决策由代码而不是 LLM 最终决定：任一必备条件未满足 → reject；否则总分 ≥ 阈值（70）→ advance；JSON 无效 → 转人工（reject 邮件不发，标记 needs_review） |
| E-1 | P0 | Paths by Zapier 分两路：advance → Gmail 发面试邀请；reject → Gmail 发拒绝信。邮件内容由决策步骤生成 |
| L-1 | P1 | 本地模拟器：用与 Zapier 相同的代码与提示词，对两份附件简历 × 两个岗位跑完整流程（真实调用 OpenAI，邮件只写到本地，不发送），用来在搭 Zap 前验证提示词和决策规则 |
| T-1 | P1 | pytest：docx 文本提取、SigV4 签名（与 botocore 对比）、DynamoDB 响应解析、JSON 校验与决策规则、邮件生成 |
| G-1 | P0 | 用户操作指南：每个账号、每个 Zap 步骤要填什么字段，逐步写清楚 |
| Q-1 | P0 | 提交 Word / PDF：代码、提示词、Zap 结构、运行截图 |

## 3. 设计

```
Google Form ──► [1] Google Forms: New Form Response
                [2] Formatter: 从上传链接提取 Drive 文件 ID
                [3] Google Drive: Retrieve File by ID
                [4] Files by Zapier: Text From File          → resume_text
                [5] Code by Zapier: get_requirements.py       → DynamoDB GetItem（SigV4）
                [6] ChatGPT (OpenAI): Send Prompt             → 评委 JSON
                [7] Code by Zapier: decide.py                 → decision、score、邮件主题和正文
                [8] Amazon DynamoDB: Create Item              → smarthire_evaluations
                [9] Paths: advance → Gmail Send Email / reject → Gmail Send Email
```

- 岗位要求的数据格式：`position`（键）、`title`、`min_years`、`mandatory`（必备条件列表）、`requirements`（其余要求）、`pass_threshold`。
- 评委模型：gpt-4.1，temperature 0。
- 测试时表单里的邮箱一律填自己的邮箱。简历里的邮箱（如 colostate.edu）可能是真实地址，不能给它们发信。
- AWS 凭证：为 Zap 单独建一个 IAM 用户，只授予这两张表的 `GetItem` / `PutItem` 权限。

## 4. 验收
- 本地模拟：Alex Carter → Software Engineer 应 advance；John Smith（幼教背景）对两个岗位都应 reject；Alex → AI Engineer 应 reject（没有 ML 经验）。
- pytest 全部通过。
- 用户在 Zapier 中按指南搭好 Zap，用两份简历各提交一次表单，收到对应邮件并截图。

## 5. 里程碑
- P0：数据与表结构、Code 步骤、提示词、决策、本地模拟、指南
- P1：测试、评估记录表
- P2：提交文档、GitHub（Zapier 截图由用户补充）

# SmartHire AI：Zapier 搭建指南

下面所有步骤都要用你自己的账号操作。要粘贴的文件都在 `E:\Project\SmartHireAI`。

Zapier 的界面会更新，按钮和字段名可能与本文略有出入，按意思找对应项即可。如果某一步对不上，把截图发给我。

---

## 第 0 步：准备账号

| 账号 | 网址 | 说明 |
| --- | --- | --- |
| Zapier | https://zapier.com/sign-up | 新账号自带约 14 天的付费版试用。本流程用到 Paths、多步 Zap 和 DynamoDB 这类高级应用，免费版可能不支持，所以请在试用期内完成 |
| Google | 用你的 Gmail 账号 | 用于 Google Forms、Google Drive、Gmail |
| AWS | https://aws.amazon.com/free | 注册需要信用卡。DynamoDB 按需计费，这点用量基本是 0 元 |
| OpenAI API key | https://platform.openai.com/api-keys | 你已经有了，就是 hw0-7 用的那个 |

---

## 第 1 步：在 AWS 中创建 DynamoDB 表并写入岗位要求（约 5 分钟）

1. 登录 https://console.aws.amazon.com/ ，右上角把区域切到 **US East (N. Virginia) us-east-1**。
2. 打开 CloudShell：https://console.aws.amazon.com/cloudshell/home?region=us-east-1 ，也可以点控制台顶栏的 `>_` 图标。
3. 用记事本打开 `E:\Project\SmartHireAI\dynamodb\setup.sh`，全选复制，粘贴到 CloudShell 回车。
   - 这一步会创建两张表：`smarthire_job_requirements`（岗位要求）和 `smarthire_evaluations`（评估记录）。
   - 然后写入 Software Engineer 和 AI Engineer 两个岗位。
   - 最后会打印一个表格，里面有 `software_engineer` 和 `ai_engineer` 两行，就说明成功了。
4. 同样地，把 `E:\Project\SmartHireAI\dynamodb\iam.sh` 粘贴到 CloudShell 回车。
   - 它会创建一个只能读写这两张表的 IAM 用户 `smarthire-zapier`。
   - 最后一行输出两段字符串：**Access key ID** 和 **Secret access key**。复制到本地记下来，后面要用，Secret 只显示这一次。
5. **截图 A：**在 DynamoDB 控制台查看岗位要求表：https://console.aws.amazon.com/dynamodbv2/home?region=us-east-1#item-explorer?table=smarthire_job_requirements ，截下两条数据。

---

## 第 2 步：创建 Google 表单（约 5 分钟）

1. 打开 https://docs.google.com/forms/ ，新建一个空白表单，标题填 `SmartHire AI – Job Application`。
2. 添加 4 个问题，**问题标题和选项文字必须和下面完全一致**：

| 问题标题 | 题型 | 设置 |
| --- | --- | --- |
| `Full name` | 简答题 | 必填 |
| `Email` | 简答题 | 必填；右下角 ⋮ → 回答验证 → 文本 → 电子邮件地址 |
| `Position` | 下拉列表 | 两个选项：`Software Engineer`、`AI Engineer`；必填 |
| `Resume` | 文件上传 | 只允许特定文件类型：勾选"文档"和 PDF；文件数量 1；大小上限 10 MB；必填 |

   - 添加文件上传题时，Google 会提示答题人必须登录 Google，点继续即可。
3. 点 **回复** 标签 → **关联到表格**（Link to Sheets）→ 新建电子表格。Zapier 有时要从这个表格读回复，先关联上更稳妥。
4. 右上角 **发布** / **发送**，复制表单链接备用。
5. **先提交一次测试回复**，给 Zapier 第 1 步测试用：
   - Full name 填 `Alex Carter`；
   - **Email 填你自己的邮箱**；
   - Position 选 `Software Engineer`；
   - Resume 上传 `E:\Project\SmartHireAI\data\resumes\hw0-09_alex_carter_resume.docx`。
6. **截图 B：**表单编辑页面，能看到 4 个问题。

> ⚠️ 测试时 Email 一律填你自己的邮箱。John 简历里的 `jwsmith@colostate.edu` 可能是真实地址，不要给它发信。

---

## 第 3 步：在 Zapier 中搭建 Zap（约 30 分钟）

打开 https://zapier.com/app/zaps ，点 **+ Create → Zaps**，把 Zap 命名为 `SmartHire AI – Resume Screening`。

### 步骤 1｜触发器：Google Forms → New Form Response
- App 选 **Google Forms**，Event 选 **New Form Response**，然后连接你的 Google 账号。
- Form 选 `SmartHire AI – Job Application`。
- 点 **Test trigger**，应该能看到第 2 步提交的那条回复。注意 Resume 字段是一个 `https://drive.google.com/open?id=...` 链接。

### 步骤 2｜Formatter by Zapier → Text → Extract Pattern
- **Input**：选步骤 1 的 `Resume` 字段。
- **Pattern**：`[-\w]{25,}`（用来取出 Drive 文件 ID）。
- 测试后输出里会有一个 25 位以上的 ID，字段名可能是 `Output 0` 或 `0`。

### 步骤 3｜Google Drive → Retrieve File or Folder by ID
- 如果找不到这个名字，选名字最接近的那个，比如 *Find a File* 或 *Get File*。
- **File ID**：选步骤 2 取出的 ID。
- 测试后应该能看到文件名 `..._alex_carter_resume.docx` 和一个 **File** 字段。

### 步骤 4｜Files by Zapier → Text From File
- **File**：选步骤 3 的 `File` 字段。
- 测试后输出的 `Text` 应该以 `Alex Carter` 和 `Software Engineer` 开头。

### 步骤 5｜Code by Zapier → Run Python（从 DynamoDB 读取岗位要求）
**Input Data** 填 5 行，左边是名字，右边是值：

| 名字 | 值 |
| --- | --- |
| `position` | 选步骤 1 的 `Position` |
| `aws_access_key` | 第 1 步记下的 Access key ID |
| `aws_secret_key` | 第 1 步记下的 Secret access key |
| `aws_region` | `us-east-1` |
| `table` | `smarthire_job_requirements` |

- **Code**：用记事本打开 `E:\Project\SmartHireAI\zapier\get_requirements.py`，全选复制粘贴进去，覆盖原有代码。
- 测试后输出应该有：`title` = `Software Engineer`、`pass_threshold` = `70`，以及以 `1. [MANDATORY] 3+ years of relevant experience` 开头的 `requirements_block`。

### 步骤 6｜ChatGPT (OpenAI) → Send Prompt（LLM 评委）
- 连接 OpenAI 账号，填入 API key。
- **Model**：`gpt-4.1`；如果没有就选 `gpt-4o`。**Temperature**：`0`；**Max tokens**：`1500`（如果有这两个选项）。
- **Instructions**（有的版本叫 System message）：打开 `E:\Project\SmartHireAI\zapier\judge_prompt.md`，复制 **Instructions** 下面代码块里的全部内容（不包括 ``` 那两行），粘贴进去。
- **User message**（或 Prompt）：复制 **User message** 代码块里的内容，然后把每个 `{{...}}` 换成插入的字段：

| 占位符 | 换成 |
| --- | --- |
| `{{today}}` | 直接输入 `{{zap_meta_human_now}}`，这是 Zapier 自带的当前时间 |
| `{{title}}` | 步骤 5 的 `title` |
| `{{requirements_block}}` | 步骤 5 的 `requirements_block` |
| `{{name}}` | 步骤 1 的 `Full name` |
| `{{resume_text}}` | 步骤 4 的 `Text` |

- 测试后的回复是一段 JSON，Alex 应得 `"recommendation": "advance"`。

### 步骤 7｜Code by Zapier → Run Python（决策和邮件内容）
**Input Data** 填 6 行：

| 名字 | 值 |
| --- | --- |
| `judge_output` | 步骤 6 的回复（字段名通常是 `Response`、`Reply` 或 `Content`） |
| `name` | 步骤 1 的 `Full name` |
| `email` | 步骤 1 的 `Email` |
| `title` | 步骤 5 的 `title` |
| `pass_threshold` | 步骤 5 的 `pass_threshold` |
| `company` | `SmartHire` |

- **Code**：粘贴 `E:\Project\SmartHireAI\zapier\decide.py` 的全部内容。
- 测试后应得到：`decision` = `advance`、`score` = `100`，以及 `email_subject`、`email_body` 等字段。

### 步骤 8｜Amazon DynamoDB → Create Item（保存评估记录）
- 连接 AWS，使用同一组 Access key 和 Secret，区域选 `us-east-1`。
- **Table**：`smarthire_evaluations`。
- 填写以下属性。如果界面要求整条 Item 的 JSON，就按下面的键值写成 `{"submission_id": "...", ...}`：

| 属性 | 值 |
| --- | --- |
| `submission_id` | 步骤 1 的 `Response ID`；没有就用 `{{zap_meta_id}}` |
| `name` / `email` / `position` | 步骤 1 的对应字段 |
| `decision` / `score` / `llm_score` / `summary` / `concerns` | 步骤 7 的对应字段 |
| `evaluated_at` | `{{zap_meta_human_now}}` |
| `evaluation_json` | 步骤 7 的 `evaluation_json` |

### 步骤 9｜Paths by Zapier（分流和发邮件）
- 添加 **Paths**，建两条路径。
- **Path A：Advance**
  - 规则：步骤 7 的 `decision`（Text）**Exactly matches** `advance`。
  - 路径里添加动作 **Gmail → Send Email**：
    - **To**：步骤 7 的 `email_to`
    - **Subject**：`email_subject`
    - **Body**：`email_body`
    - **Body type**：Plain
- **Path B：Reject**
  - 规则：`decision` **Exactly matches** `reject`。
  - 同样添加一个 Gmail → Send Email，字段映射和上面一样。
- `needs_review`（评委输出无法解析）两条路径都不会进入，所以不会发出错误的邮件。

点 **Publish**，把 Zap 打开。

---

## 第 4 步：端到端测试

用同一个表单再提交 3 次，Email 都填你自己的邮箱：

| # | Full name | Position | Resume | 预期结果 |
| --- | --- | --- | --- | --- |
| 1 | Alex Carter | Software Engineer | `hw0-09_alex_carter_resume.docx` | 收到面试邀请邮件（advance） |
| 2 | John W. Smith | Software Engineer | `hw0-09_john_smith_resume.docx` | 收到拒绝邮件（reject） |
| 3 | Alex Carter | AI Engineer | `hw0-09_alex_carter_resume.docx` | 收到拒绝邮件（没有 AI/ML 经验） |

Google Forms 触发器是轮询的，提交后 1–15 分钟内 Zap 才会运行，取决于套餐。可以在 Zap 编辑器里点 **Run** 加快。

运行记录在这里看：https://zapier.com/app/history

---

## 第 5 步：需要的截图（发给我，我放进文档）

| 编号 | 内容 | 在哪里 |
| --- | --- | --- |
| A | DynamoDB 岗位要求表的两条数据 | DynamoDB 控制台 → Explore items → `smarthire_job_requirements` |
| B | Google 表单编辑页 | Google Forms |
| C | Zap 编辑器的全貌（能看到所有步骤和两条 Path） | Zapier 编辑器 |
| D | 步骤 6 的测试结果（评委 JSON） | Zapier 编辑器 → 步骤 6 → Test |
| E | 步骤 7 的测试结果（decision 和 score） | Zapier 编辑器 → 步骤 7 → Test |
| F | 一次成功运行的详情（每一步都是绿色） | https://zapier.com/app/history |
| G | 收到的两封邮件：advance 一封、reject 一封 | 你的 Gmail 收件箱 |
| H | 评估记录表里的数据 | DynamoDB → Explore items → `smarthire_evaluations` |

截图里不要露出 AWS Secret key 和 OpenAI API key。

---

## 常见问题

- **步骤 5 报 403 / AccessDenied**：Access key 填错，或者区域不是 `us-east-1`。
- **步骤 5 报 `no job requirements for position`**：表单里 Position 选项的文字和 `Software Engineer` / `AI Engineer` 不一致。
- **步骤 5 报超时**：免费版的 Code 步骤只能运行 1 秒，试用版或付费版是 10 秒以上。
- **步骤 7 输出 `needs_review`**：评委没有返回合法 JSON。检查步骤 6 的 Instructions 是否完整粘贴，Max tokens 是否太小。
- **步骤 4 读出来是空的**：检查步骤 3 传的是不是 `File` 字段，而不是文件名或链接文本。

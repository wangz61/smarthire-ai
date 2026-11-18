# Homework 0-10 操作指南：API Gateway + Lambda + Zapier Webhooks

在 0-9 已经跑通的 Zap 上只改两步：第 5 步（读岗位要求）和第 8 步（保存评估）都从 Code by Zapier 换成 **Webhooks by Zapier**，请求经 API Gateway 转给 Lambda，再由 Lambda 访问 DynamoDB。

```
Zapier Webhooks (GET/POST) ──x-api-key──► API Gateway (HTTP API) ──► Lambda smarthire-api ──IAM 角色──► DynamoDB
```

## 第 1 步：部署 Lambda 和 API Gateway（约 3 分钟）

1. 打开 AWS CloudShell：https://us-east-1.console.aws.amazon.com/cloudshell/home?region=us-east-1 （区域和 0-9 的两张表一致，us-east-1）。
2. 在本机用记事本打开 `lambda/deploy.sh`，全选、复制，粘贴到 CloudShell，按回车。
3. 运行结束时会打印：
   ```
   --- GET /requirements without a key (expect 401)
   401
   --- GET /requirements?position=Software Engineer
   {"position": "software_engineer", "title": "Software Engineer", ... }
    API base URL : https://xxxxxxxx.execute-api.us-east-1.amazonaws.com
    x-api-key    : ........
   ```
   记下 **API base URL** 和 **x-api-key**。截图时把 key 打码。
4. 可选：再测一下排名接口
   ```bash
   curl -s -H "x-api-key: <你的key>" "<API base URL>/rankings?position=software_engineer"
   ```

脚本可以重复运行：再次运行会更新代码，并保留原来的 key。

## 第 2 步：修改 Zap 第 5 步：Webhooks by Zapier → GET

1. 在 Zap 编辑器里点第 5 步（Code by Zapier），右上角 ⋯ → **Change app**（或者删掉它，在原位置加一步）。
2. App 选 **Webhooks by Zapier**，Event 选 **GET**。
3. Configure：

| 字段 | 填写 |
| --- | --- |
| URL | `<API base URL>/requirements` |
| Query String Params | 左边 `position`，右边映射第 1 步表单的 **Position**（申请岗位） |
| Send As JSON | No |
| Headers | 左边 `x-api-key`，右边粘贴 key |
| 其余 | 默认 |

4. Test step。返回 `title`、`pass_threshold`、`requirements_block` 等，字段名和原来的 Code 步骤完全一样。
5. **重新映射后面的步骤**：第 6 步（ChatGPT）里的 `title`、`requirements_block`，第 7 步（decide）里的 `title`、`pass_threshold`，都要改为从这个新的第 5 步取值（原来那一步已经不存在，旧映射会显示为失效）。

## 第 3 步：修改 Zap 第 8 步：Webhooks by Zapier → POST

1. 第 8 步（save_evaluation 的 Code 步骤）同样 Change app → **Webhooks by Zapier**，Event 选 **POST**。
2. Configure：

| 字段 | 填写 |
| --- | --- |
| URL | `<API base URL>/evaluations` |
| Payload Type | **json** |
| Data | `submission_id` = `{{zap_meta_id}}`（或表单 Response ID）；`name`、`email`、`position` = 表单字段；`decision`、`score`、`llm_score`、`timeline_flag`、`summary`、`concerns`、`evaluation_json` = 第 7 步对应字段；`evaluated_at` = `{{zap_meta_human_now}}` |
| Headers | `x-api-key` = 你的 key |

3. Test step，返回 `{"saved": true, "table": "smarthire_evaluations", "submission_id": ..., "attributes": ...}`。

## 第 4 步：收尾

1. 现在 Zap 里已经没有任何 AWS 密钥了。到 IAM → Users → `smarthire-zapier` → Security credentials，**删除旧的 access key**（包括截图里泄露过的那一个）。也可以直接删除这个用户。
2. Publish Zap，用 Alex 和 John 的简历各提交一次表单，确认收到邮件。

## 第 5 步：需要的截图（放进 `docs/hw10/`，发给我也行）

| 文件名 | 内容 |
| --- | --- |
| `A-cloudshell-deploy.png` | CloudShell 运行 deploy.sh 的最后输出（401 + 返回的 JSON，key 打码） |
| `B-lambda.png` | Lambda 控制台 smarthire-api 页面（上面能看到 API Gateway 触发器） |
| `C-api-gateway.png` | API Gateway → smarthire-api 的路由或 stage 页面 |
| `D-zap-webhook-get.png` | Zap 第 5 步 Webhooks GET 的测试结果 |
| `E-zap-webhook-post.png` | Zap 第 8 步 Webhooks POST 的测试结果 |
| `F-zap-overview.png` | 整个 Zap 的流程图 |
| `G-rankings.png` | 可选：`/rankings` 的 curl 输出 |

## 常见问题

- **401**：Header 名必须是 `x-api-key`，值前后不能有空格。
- **404 no job requirements**：表单里岗位的选项应为 `Software Engineer` 或 `AI Engineer`，Lambda 会自动转成 `software_engineer`。
- **500 AccessDeniedException**（在 CloudWatch 日志里）：Lambda 和表不在同一区域，或者表名不一致。
- **Webhooks 的字段在后面的步骤里找不到**：先对第 5 步点一次 Test step，Zapier 才会知道返回了哪些字段。

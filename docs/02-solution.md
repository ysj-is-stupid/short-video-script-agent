# 02 方案与详细设计

## 技术选择

- Python 3.13，兼容 Python 3.11 及以上。
- LangGraph 1.2.20：状态、节点、循环、路由和终止。
- Pydantic 2.12.4：请求、动作、工具结果与最终结果校验。
- OpenAI SDK 2.54.0：OpenAI 原生及 DeepSeek OpenAI 兼容接口客户端。
- pytest 8.4.2：单元、图与 CLI 测试。

选择 LangGraph 的原因是本题需要维护素材、脚本修订版、时长报告、规则报告和预算，并多次返回模型决策节点。显式 `StateGraph` 使循环和终止条件可直接审查。

## 调用流程

```text
START
  → prepare_context
  → budget_before_model
  → agent_decide
  → apply_decision
      ├─ 工具动作 → budget_before_tool → execute_tool
      │                              → record_observation
      │                              → budget_before_model
      ├─ finish → completion_guard
      │              ├─ 通过 → terminalize → END
      │              └─ 拒绝 → budget_before_model
      └─ request_input/fail → terminalize → END
```

条件边只根据模型已经选择的动作路由。检索为空后使用什么新查询、时长超限后如何压缩、规则不通过后如何修改，均由下一次模型决策决定。

## 状态与动作

`AgentState` 保存请求、缺失字段、规则、检索历史、素材、当前脚本、检查报告、最近观察、待执行动作、计数、状态、风险和 Trace。

脚本有 `revision` 和内容 `fingerprint`。两个检查报告同时绑定这两个值，脚本改变后旧报告失效。

模型只能选择 `search_materials`、`estimate_duration`、`check_rules`、`finish`、`request_input` 或 `fail`。生成或修订稿随检查动作提交，避免绕过工具完成。

## 工具

素材检索使用本地确定性关键词，空结果为 `empty`，执行故障为 `error`。

时长工具按中文每秒 4 个汉字、英文每分钟 150 词估算，并为每个镜头加入 0.5 秒切换时间。

规则工具检查素材和事实 ID、事实归属、无依据数字、品牌禁用词、必需词和产品事实来源。它不能完成开放世界语义核验。

## 完成守卫与预算

只有当前脚本版本的时长与规则报告都通过、引用有效且无 error 违规时才能完成。守卫拒绝时只返回观察，不替模型决定下一动作。

默认最多 10 次模型决策、8 次工具调用和 2 次无效动作。业务预算在框架递归限制之前返回明确 `incomplete`。

## 模型接入

`LiveModelAdapter` 是供应商无关的真实模型边界。真实模型与 Mock 均返回相同的 Pydantic `AgentDecision`，因此图、工具、完成守卫和 Trace 不依赖具体模型供应商。

OpenAI 原生路径使用 Responses API 的 `responses.parse`，直接以 `AgentDecision` 作为结构化输出类型。

DeepSeek 路径使用 OpenAI 兼容的 Chat Completions 接口，请求 JSON Object，再用 `AgentDecision.model_validate_json` 做本地 Schema 校验。DeepSeek 没有被描述或调用为 Responses API。

程序支持以下配置：

- OpenAI：`OPENAI_API_KEY`、`OPENAI_MODEL` 和可选 `OPENAI_BASE_URL`。
- DeepSeek：`DEEPSEEK_API_KEY`、`DEEPSEEK_MODEL` 和 `DEEPSEEK_BASE_URL`。
- 可选 `MODEL_PROVIDER` 可以显式指定供应商；否则检测到 DeepSeek 配置时选择 DeepSeek，其余情况选择 OpenAI。
- 默认固定选择 `mock`；凭据存在不会授权联网。只有显式设置 `MODEL_MODE=live` 或 CLI `--model-mode live` 才选择真实模型。

仓库根目录 `.env` 会自动加载，当前 Shell 环境变量优先于文件值。`.env` 被 Git 忽略，仓库只提交不含密钥的 `.env.example`。忽略规则不能防止强制添加、压缩打包或人工复制，因此交付前仍需执行工作区秘密扫描；已暴露的凭据必须在供应商后台轮换。

传输错误与输出错误分开处理：连接、超时、限流和服务端错误形成 `model_request_error`；已返回但 JSON/Schema 无效的内容形成 `decision_error` 并消耗无效动作预算。

Trace Schema 2.0 分离 `proposed_tool_args` 与 `executed_tool_args`：前者保留模型原始提议，后者是执行节点允许并规范化后真正传给工具的参数。搜索只允许 `query`、`product_name`、`scope_ids` 和 `limit`，未知字段不会再显示为已执行。真实模型 Trace 还记录 provider、模型名、SDK/应用版本和可用响应 ID，不记录密钥或 Base URL。

`requested_fields` 由枚举约束为机器字段标识，自然语言补充要求写入 `requested_details`。产品素材支持显式 `aliases`；规则检查只把效果型数字作为主张数字，自动允许事实原文中的数字，并使用短语正则降低风险词子串误伤。每次再次提交稿件都必须严格递增 revision。完成稿低于目标时长 70% 时保留完成状态，但输出明确偏短风险。

离线 `ScriptedMockAdapter` 读取相同状态与观察，但策略预设，只用于可复现测试。

## Trace

每个模型动作、工具观察、守卫结果和终态都会写入节点事件。评审视图从实际相邻事件关联“工具结果 → 后续动作”，不预写决策日志。

更细设计见 [design 目录](design/)。


# 阶段 5：核心 ReAct 链路

## 阶段状态

- 状态：已完成并通过后续全量验证
- 目标：实现可运行的“模型选择动作 → 工具执行 → 观察结果 → 模型调整或结束”循环
- 实际用时：约 45 分钟

## 本阶段实现范围

1. 实现素材检索、时长估算和品牌规则检查三个本地工具。
2. 实现工具注册、统一异常观察及可控故障注入。
3. 实现按场景驱动的 Scripted Mock，使离线运行可复现多条状态路径。
4. 实现 OpenAI Responses API 结构化决策适配器。
5. 实现 LangGraph 节点、条件路由、显式预算和完成守卫。
6. 将 CLI 接入 JSON 输入、JSON 输出和结构化 Trace。
7. 添加核心链路测试，验证工具结果变化会导致后续动作变化。

## 核心循环设计

```text
START
  → prepare_context
  → budget_guard
  → agent_decide
  → apply_decision
      ├─ tool action → execute_tool → record_observation → budget_guard → agent_decide
      ├─ finish → completion_guard
      │              ├─ accepted → terminalize → END
      │              └─ rejected → budget_guard → agent_decide
      └─ request_input/fail → terminalize → END
```

条件路由只读取模型动作类型。检索为空后改写什么查询、时长超限后提交什么修订稿、规则失败后是否继续修改，均由模型适配器返回下一动作。

## 离线 Mock 边界

Mock 会读取当前观察并返回下一动作，因此可以验证图确实把工具结果反馈给模型接口；但其策略由测试场景预设，只证明流程和状态转换，不证明真实模型决策质量。

## 真实模型接入

- 使用已安装 OpenAI SDK 的 Responses API `responses.parse`。
- 以 `AgentDecision` 作为结构化输出类型。
- 模型名和密钥只从环境配置读取。
- 无密钥或模型名时明确报配置错误，不回退为伪造的真实模式。
- 官方文档页面在当前网络环境被站点防护拦截；实现依据本地安装的 OpenAI SDK 2.54.0 方法签名核对，并在最终文档中保留该验证边界。

## 工具最小可用行为

### 素材检索

- 从注入的本地素材集合中按查询、标签、产品名和范围过滤。
- 空结果与执行错误使用不同 `result_kind`。

### 时长估算

- 对每个分镜选择旁白文本；无旁白时使用字幕。
- 中文按字符速率估算，英文按词速率估算。
- 每个镜头加入最小切换时长，结果可复现。

### 规则检查

- 校验素材 ID、事实 ID 及归属关系。
- 校验无依据的数字和百分比。
- 校验禁用词、必需词和产品事实来源。
- 输出错误与警告；只有错误为空时 `passed=true`。

## 完成条件

完成守卫沿用详细设计的七项条件。任何新脚本修订都会使旧检查报告失效；守卫只返回缺失条件观察，不替模型选择下一工具。

## 验证重点

1. 首稿超时时，下一动作提交新修订并再次估时。
2. 检索为空时，下一动作使用不同查询再次检索。
3. 未检查或报告过期时，`finish` 被守卫拒绝。
4. 达到模型或工具预算时返回 `incomplete`，而非抛出框架递归异常。
5. Trace 能把工具参数、返回摘要、下一动作和公开依据串联起来。

## 不在本阶段完成

- 完整五类验收材料和最终示例归档。
- 最终 `docs/01-05` 文档整理。
- 全量测试报告、GitHub 远程仓库与最终 commit SHA。

## 实际实现结果

### LangGraph 循环

已实现并编译以下节点：

- `prepare_context`
- `budget_before_model`
- `agent_decide`
- `apply_decision`
- `budget_before_tool`
- `execute_tool`
- `record_observation`
- `completion_guard`
- `terminalize`

模型动作经过结构校验后才会进入路由。工具结果写入 `last_observation` 后重新进入模型节点。完成守卫只接受当前脚本版本对应的时长报告和规则报告。

### 动态路径一：时长修正

实际动作序列：

```text
search_materials
→ estimate_duration（revision 1，38.1 秒，未通过）
→ estimate_duration（revision 2，28.0 秒，通过）
→ check_rules（通过）
→ finish
```

首稿工具观察包含 `within_limit=false`。下一次模型接口调用提交压缩稿并再次选择估时；不是工具内部自动压缩或自动重试。

参考要求中的“38 秒”在工具中保留一位小数后为 38.1 秒，评审显示时可理解为约 38 秒；修订结果为 28.0 秒。

### 动态路径二：无素材

实际动作序列：

```text
search_materials（首次为空）
→ search_materials（使用不同查询再次检索，仍为空）
→ request_input
```

最终状态为 `needs_input/no_supporting_materials`，请求补充 `product_materials`，没有生成产品脚本。

### 守卫与预算

- 未执行检查便 `finish` 会生成 `guard_rejected` 观察并回到模型节点。
- 达到工具调用上限返回 `incomplete/tool_call_limit_reached`。
- 达到模型决策上限返回 `incomplete/model_step_limit_reached`。
- 两种上限都在 LangGraph 递归异常之前产生业务可读结果。

### 工具

- 素材检索能区分成功、空结果和可重试错误。
- 时长工具使用固定语速和镜头切换参数，输出分镜及总时长。
- 规则工具检查素材/事实归属、无依据数字、禁用词、必需词和产品事实引用。
- `效率提升80%` 在 P01 未提供数据时会产生 `unsupported_numeric_claim`。

### 模型适配器

- `ScriptedMockAdapter` 根据最近工具观察选择下一动作，并在 Trace 中明确标记 Mock 边界。
- `OpenAIModelAdapter` 使用 OpenAI SDK 2.54.0 的 `responses.parse` 和 `AgentDecision` Pydantic 类型请求结构化输出。
- 当前环境未配置 `OPENAI_API_KEY` 和 `OPENAI_MODEL`，因此没有执行真实模型调用；缺少配置时会明确失败，不静默回退为 Mock。
- OpenAI 官方文档页面在当前网络环境被站点防护拦截；调用形状通过本地 SDK 2.54.0 的实际方法签名核对。

### CLI 与 Trace

CLI 已支持：

```text
short-video-agent run
  --input
  --materials
  --rules
  --model-mode
  --scenario
  --output
  --trace
  --simulate-search-failures
```

Trace 同时包含：

- 原始 LangGraph 节点事件。
- 评审视图：工具参数、返回摘要、实际发生的下一动作、公开决策依据和脚本修订号。
- `model_mode` 与 Mock 能力边界。

## 测试结果

执行：

```powershell
python -m compileall -q src
python -m pytest -q
```

实际结果：`15 passed`。

新增测试覆盖：

1. 时长观察导致脚本修订和第二次估时。
2. 空检索结果导致查询改写和请求补充。
3. 完成守卫拒绝未经检查的完成动作。
4. 工具调用预算返回明确未完成状态。
5. 模型步数预算返回明确未完成状态。
6. 素材检索成功与空结果。
7. 超时长工具结果。
8. 无依据数字规则违规。
9. CLI 实际写出结果与 Trace。

## 关键实现文件

- `src/short_video_agent/graph.py`
- `src/short_video_agent/runtime.py`
- `src/short_video_agent/model/openai_adapter.py`
- `src/short_video_agent/model/scripted_mock.py`
- `src/short_video_agent/tools/material_search.py`
- `src/short_video_agent/tools/duration_estimator.py`
- `src/short_video_agent/tools/rule_checker.py`
- `src/short_video_agent/trace.py`
- `src/short_video_agent/cli.py`
- `tests/test_core_react.py`
- `tests/test_tools.py`
- `tests/test_cli.py`

## 阶段边界复核

本阶段当时没有提交正式 `data/` 合成资料，没有在 `examples/` 固化验收输入、输出和 Trace，也没有整理最终 `docs/01-requirements.md` 至 `05-retrospective.md`；这些内容已在后续阶段完成并经第二轮审计扩充。

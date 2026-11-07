# 阶段 3：详细设计

## 阶段状态

- 状态：设计完成，后续实现与验收已完成
- 目标：将已确认的总体方案细化为可直接实现和测试的契约

## 1. 设计原则

1. 模型负责业务动作选择，图只执行和约束动作。
2. 每次工具执行结果都作为下一次模型调用的观察输入。
3. 脚本修订版与时长、规则报告强绑定，旧报告不能用于新脚本完成。
4. 工具的“无结果”“业务不通过”“执行异常”使用不同结果类型。
5. 所有终止都必须有明确状态和机器可读原因。
6. Trace 只记录简短的公开决策依据，不要求或保存模型内部思维过程。
7. 真实模型与 Mock 共用状态、动作、工具和完成守卫。

## 2. 目录职责预案

本节只定义后续工程骨架，不在本阶段创建这些文件。

```text
src/short_video_agent/
  cli.py                 # CLI 参数、文件读写和退出码
  config.py              # 模型、预算和估时参数
  graph.py               # StateGraph 构建及条件路由
  state.py               # AgentState 和 Reducer
  schemas.py             # 请求、脚本、动作、报告和结果模型
  prompts.py             # 系统提示与状态摘要构造
  model/
    base.py              # ModelAdapter 协议
    openai_adapter.py    # 真实模型结构化输出
    scripted_mock.py     # 离线场景适配器
  tools/
    material_search.py
    duration_estimator.py
    rule_checker.py
    registry.py
  trace.py               # 事件记录与评审视图导出
  errors.py              # 应用错误和错误码
tests/
examples/
data/
docs/
```

## 3. 输入模型

### `ScriptRequest`

| 字段 | 传输层类型 | 业务必填 | 规则 |
| --- | --- | --- | --- |
| `topic` | `str | null` | 是 | 非空时去除首尾空白；空值进入缺信息路径 |
| `audience` | `str | null` | 是 | 非空时去除首尾空白；空值进入缺信息路径 |
| `platform` | `str | null` | 是 | 例如抖音、视频号、小红书；不限制为封闭枚举 |
| `target_duration_seconds` | `int | null` | 是 | 非空时大于 0，初版上限 600 秒 |
| `style` | `str | null` | 是 | 非空时去除首尾空白；空值进入缺信息路径 |
| `product_name` | `str | null` | 否 | 用于缩小素材范围 |
| `material_scope_ids` | `list[str]` | 否 | 为空表示在全部本地素材内检索 |
| `brand_rule_scope_ids` | `list[str]` | 否 | 为空表示加载全部适用规则 |

CLI 负责 JSON 语法和基础类型校验。上述业务必填字段在传输 Schema 中允许缺失或为 `null`，以便形成题目要求的缺信息 Agent 路径；它们不会被静默填入业务默认值，而是写入 `missing_fields` 观察，由模型选择 `request_input`。明显非法值（例如字符串类型的时长或负时长）直接返回输入错误，不启动图。

## 4. 素材与品牌规则模型

### `Material`

- `material_id`：稳定来源 ID，例如 `P01`。
- `product_name`：所属产品。
- `aliases`：显式声明的产品简称或别名；检索仍以正式名精确匹配优先。
- `title`：素材标题。
- `facts`：结构化事实列表。
- `tags`：用于本地检索的关键词。

### `MaterialFact`

- `fact_id`：例如 `P01-F01`。
- `statement`：素材原始事实，例如“支持字幕”。
- `keywords`：用于检索和规则检查的辅助词。
- `allowed_numbers`：该事实明确允许出现的规范化数字或比例；事实原文自身包含的效果数字也自动纳入允许值。

### `BrandRule`

- `rule_id`
- `description`
- `severity`：`error` 或 `warning`
- `forbidden_terms`
- `required_terms`
- `applies_to_platforms`

合成数据只表达仓库内可验证的事实，不包含真实用户数据或真实密钥。

## 5. 脚本模型

### `ScriptDraft`

- `revision`：从 1 开始，每次内容变化递增。
- `title`
- `scenes: list[Scene]`
- `fingerprint`：由规范化后的标题和分镜内容计算，用来关联检查报告。

### `Scene`

- `scene_id`：稳定顺序 ID，例如 `S01`。
- `visual`：画面描述。
- `narration`：旁白，可为空。
- `subtitle`：字幕，可为空。
- `source_ids`：本镜头使用的素材 ID。
- `fact_ids`：本镜头表达的产品事实 ID。
- `estimated_seconds`：由时长工具写入，模型提供的值不被信任。

纯情绪、转场或行动号召可以没有 `source_ids` 和 `fact_ids`，但只要表达产品能力、效果或数据，就必须提供对应事实 ID。

## 6. Agent 状态

`AgentState` 计划包含：

| 字段 | 说明 |
| --- | --- |
| `request` | 规范化请求 |
| `missing_fields` | 缺失的关键输入字段 |
| `applicable_rules` | 本次任务适用的品牌规则 |
| `query_history` | 已执行过的检索词及结果摘要 |
| `retrieved_materials` | 已获取的素材与事实 |
| `draft` | 最新脚本修订版 |
| `duration_report` | 最新时长报告 |
| `rule_report` | 最新规则报告 |
| `last_observation` | 最近一次工具或守卫观察 |
| `pending_decision` | 当前待执行的模型动作，仅用于节点间传递 |
| `pending_tool_result` | 尚未写回观察状态的工具结果 |
| `pending_tool_args` | 执行节点规范化后真正传给工具的参数 |
| `model_step_count` | 已完成的模型决策次数 |
| `tool_call_count` | 已执行的业务工具次数 |
| `invalid_decision_count` | 无效模型动作次数 |
| `status` | 当前任务状态 |
| `risks` | 面向用户的风险列表 |
| `terminal_reason` | 机器可读终止原因 |
| `terminal_message` | 用户可读终止说明 |
| `requested_fields` | 需要用户补充的字段 |
| `requested_details` | 面向用户的自然语言补充说明 |
| `trace_events` | 追加式执行事件 |
| `result` | `terminalize` 生成的最终结果 |

列表字段使用追加 Reducer，单值字段使用最新值覆盖。状态中不存储模型隐藏推理。

## 7. 模型动作协议

### `AgentDecision`

- `action`：动作枚举。
- `public_reason`：一句简短、可展示的动作依据。
- `based_on_observation_id`：本次决策依据的观察事件 ID。
- `tool_args`：工具动作参数；终止动作为空。
- `draft`：本次生成或修订的脚本；未修改时为空。
- `requested_fields`：请求补充时需要的字段。
- `requested_details`：自然语言补充要求；`requested_fields` 只允许机器枚举值。
- `terminal_message`：终止动作的用户可读说明。

### 动作枚举

- `search_materials`
- `estimate_duration`
- `check_rules`
- `finish`
- `request_input`
- `fail`

不单设 `generate_script` 或 `revise_script` 工具。模型在选择 `estimate_duration` 或 `check_rules` 时可以同时提交新的 `draft`。这样首稿和修订稿都会立即进入工具观察循环，不会出现“生成后未经检查直接完成”的旁路。

### 动作校验

- 工具动作必须提供对应参数。
- `estimate_duration` 和 `check_rules` 必须存在当前稿或随动作提交新稿。
- 每次再次提交稿件时 `revision` 必须严格递增，即使内容指纹不变；系统重新计算 `fingerprint`。
- `request_input` 必须包含非空 `requested_fields`。
- `finish` 不接受模型自行声明的检查结果，只读取状态中的工具报告。
- 动作结构无效时记录 `invalid_decision` 观察并回到模型；超过无效动作预算则 `failed`。

## 8. 工具协议

所有工具返回统一外壳：

- `tool_name`
- `call_id`
- `ok`
- `result_kind`
- `summary`
- `data`
- `error_code`
- `retryable`

`result_kind` 区分：

- `success`
- `empty`
- `rejected`
- `error`
- `timeout`

### 8.1 素材检索 `search_materials`

输入：

- `query`
- `product_name`
- `scope_ids`
- `limit`

输出数据：

- `matches`
- 每条匹配的 `material_id`、命中事实、匹配关键词和简短得分

约束：

- 无命中返回 `ok=true, result_kind=empty`。
- 存储读取失败返回 `ok=false, result_kind=error`。
- 相同查询允许再次调用，但 Trace 会显示重复；预算不豁免。

### 8.2 时长估算 `estimate_duration`

输入：

- `draft`
- `platform`
- `target_duration_seconds`

输出数据：

- `draft_revision`
- `draft_fingerprint`
- `scene_durations`
- `total_seconds`
- `target_seconds`
- `over_by_seconds`
- `within_limit`
- `estimation_method`

估时原则：

- 按实际输出语言使用可配置的字符或词语速率。
- 取旁白和字幕中需要朗读或展示的主要文本，避免简单双重相加。
- 每个分镜加入最小镜头切换时间。
- 结果统一舍入，算法和参数写入报告，保证可复现。
- 模型不能覆盖工具计算的 `estimated_seconds`。

### 8.3 规则检查 `check_rules`

输入：

- `draft`
- `retrieved_materials`
- `applicable_rules`

输出数据：

- `draft_revision`
- `draft_fingerprint`
- `passed`
- `violations`
- `warnings`
- `checked_source_ids`

每条违规项包含：

- `code`
- `severity`
- `scene_id`
- `message`
- `related_source_ids`
- `related_fact_ids`

首版确定性检查范围：

1. 引用的素材和事实 ID 是否存在。
2. `fact_id` 是否属于声明的 `source_id`。
3. 产品相关数字或百分比是否出现在对应素材事实的允许数据中。
4. 是否包含品牌禁用词。
5. 是否缺少品牌要求词。
6. 分镜 ID、标题、旁白或字幕等结构是否完整。
7. 产品事实镜头是否缺少来源。

确定性检查不能完全证明自由文本与素材在语义上等价。该边界必须在风险中披露，并通过真实模型集成用例观察是否出现非数字类事实扩写。

## 9. LangGraph 节点设计

### `prepare_context`

- 规范化输入。
- 识别缺失关键字段。
- 加载适用品牌规则。
- 生成初始观察。

### `budget_guard`

- 在模型调用和工具执行前检查预算。
- 达到模型步数上限：设置 `incomplete/model_step_limit_reached`。
- 达到工具调用上限：设置 `incomplete/tool_call_limit_reached`。
- 未超限则继续。

### `agent_decide`

- 向 `ModelAdapter` 提供请求、素材摘要、当前稿、最新报告、最近观察和剩余预算。
- 获得并校验 `AgentDecision`。
- 递增 `model_step_count`。
- 记录决策事件。

### `apply_decision`

- 接纳合法的新脚本修订版并计算指纹。
- 根据动作准备工具参数或终止候选。
- 不执行业务工具。

### `execute_tool`

- 通过白名单注册表调用三个业务工具之一。
- 捕获超时和异常并转换为统一工具结果。
- 每次实际调用递增 `tool_call_count`，包括失败调用。

### `record_observation`

- 将工具结果写入对应报告或检索历史。
- 生成短摘要并记录 Trace。
- 返回 `budget_guard` 后再次进入模型决策。

### `completion_guard`

- 校验完成条件。
- 通过时设置 `completed`。
- 不通过时生成 `finish_rejected` 观察，返回模型继续决策。

### `terminalize`

- 处理 `request_input`、`fail` 和预算终止。
- 形成统一 `AgentResult`。

## 10. 图与路由

```text
START
  → prepare_context
  → budget_guard
      ├─ budget exhausted → terminalize → END
      └─ continue → agent_decide
          → apply_decision
              ├─ search/estimate/check → budget_guard
              │                           ├─ exhausted → terminalize → END
              │                           └─ execute_tool
              │                               → record_observation
              │                               → budget_guard
              ├─ finish → completion_guard
              │              ├─ accepted → terminalize → END
              │              └─ rejected → budget_guard
              └─ request_input/fail → terminalize → END
```

路由依据是模型动作类型和守卫结果。检索为空后是否改写查询、时长超限后如何压缩、规则失败后是否修改，均由下一次模型决策决定。

## 11. 完成守卫

只有同时满足以下条件才能 `completed`：

1. 存在非空脚本和至少一个分镜。
2. 存在与当前 `revision` 和 `fingerprint` 一致的时长报告。
3. `duration_report.within_limit=true`。
4. 存在与当前稿一致的规则报告。
5. `rule_report.passed=true`。
6. 所有引用的素材和事实 ID 都有效。
7. 不存在 `error` 级别规则违规。

模型提交新修订版后，旧时长报告和旧规则报告立即视为过期。完成守卫拒绝时返回具体缺项，但不直接替模型选择下一工具。

## 12. 执行预算

初始默认值：

- `max_model_steps = 10`
- `max_tool_calls = 8`
- `max_invalid_decisions = 2`

这些值允许完成“检索 → 估时 → 修订 → 再估时 → 规则检查 → 修订 → 再检查”，同时能阻止无限循环。

LangGraph `recursion_limit` 设置为高于业务预算所需节点数的保险值。业务预算必须先产生明确的 `incomplete`；不依赖框架异常作为正常终止方式。

## 13. 任务状态与终止原因

### `completed`

- `all_checks_passed`

### `needs_input`

- `missing_required_fields`
- `no_supporting_materials`
- `ambiguous_user_constraint`

### `incomplete`

- `model_step_limit_reached`
- `tool_call_limit_reached`

### `failed`

- `model_output_invalid`
- `tool_unavailable`
- `tool_timeout`
- `constraints_unsatisfiable`
- `internal_error`

终止结果包含用户可读说明、可恢复建议和剩余风险。

## 14. 最终结果模型

`AgentResult` 包含：

- `status`
- `terminal_reason`
- `title`
- `scenes`
- `estimated_total_seconds`
- `target_duration_seconds`
- `source_ids`
- `duration_check`
- `rule_check`
- `risks`
- `requested_fields`
- `requested_details`
- `message`
- `trace_file`

非 `completed` 状态允许返回已有草稿，但必须明确标为未通过最终检查，不能伪装成已交付脚本。

## 15. Trace 设计

### 原始事件 `TraceEvent`

- `event_id`
- `sequence`
- `timestamp`
- `node`
- `event_type`
- `model_step`
- `tool_call_count`
- `action`
- `public_reason`
- `tool_name`
- `proposed_tool_args`
- `executed_tool_args`
- `model_response_id`
- `result_kind`
- `result_summary`
- `draft_revision`
- `status_after`
- `based_on_observation_id`

敏感字段和密钥不写入 Trace。长文本参数保存摘要或引用文件路径。

### 评审视图

原始事件会被整理为逐步记录，每步包含：

- 步骤编号
- 模型提议的工具参数
- 执行节点规范化后实际调用工具的参数
- 工具返回摘要
- 后续动作
- 简短决策依据
- 对应脚本修订版

“后续动作”通过相邻决策事件关联生成，避免在工具尚未执行时预设日志。

## 16. 模型适配器

统一协议：

```text
decide(decision_context) -> AgentDecision
```

### 真实模型适配器

- 使用结构化输出生成 `AgentDecision`。
- 提示中明确动作列表、工具说明、剩余预算、事实引用规则和终止条件。
- 只传递必要状态摘要，避免不断累积完整提示。
- API 失败转换为模型调用错误，不写入业务工具调用次数。
- 暴露非秘密 `trace_metadata` 和最近一次 response ID，记录 provider、模型名、SDK/应用版本；不记录 Key 或 Base URL。

### Scripted Mock

- 根据场景名和最近观察返回预设的合法动作。
- 用于离线端到端测试和固定 Trace。
- 输出中明确 `model_mode=mock`。
- Mock 结果只能证明图、工具和守卫按预期工作，不能证明真实模型具备相同决策能力。

## 17. 验收场景详细映射

### `normal_duration_revision`

- 素材 P01 只包含“支持字幕”。
- 目标 30 秒。
- 首稿估时 38 秒。
- 模型观察后提交压缩版，再估时 28 秒。
- 规则通过后完成。
- 断言：输出包含分镜、P01、28 秒和两次估时记录，不包含“效率提升 80%”。

### `missing_required_information`

- 缺少受众或目标时长。
- 模型选择 `request_input`。
- 断言：`needs_input`、缺失字段明确、未调用脚本检查工具。

### `no_materials_after_query_rewrite`

- 首次检索无结果。
- 模型改写查询并再次检索。
- 第二次仍为空后请求补充素材。
- 断言：两次查询不同、状态为 `needs_input`、没有编造产品事实。

### `tool_failure`

- 素材检索工具返回可重试错误。
- 模型选择一次重试；再次失败后选择 `fail`。
- 断言：错误与空结果可区分，终态和原因明确，调用次数正确。

### `unsupported_claim_revision`

- 首稿加入无素材依据的“效率提升 80%”。
- 规则检查拒绝。
- 模型删除该事实并再次检查。
- 断言：最终稿无该结论，规则检查存在失败和通过两次记录。

## 18. 测试策略

### 单元测试

- 素材检索成功、空结果、范围过滤和异常。
- 中文时长估算、分镜合计和舍入。
- 引用有效性、数字事实、禁用词和必需词检查。
- Pydantic 输入、动作和结果校验。

### 图测试

- 每个动作路由到正确节点。
- 工具观察能回到模型节点。
- 新修订版会使旧报告失效。
- 完成守卫拒绝缺少检查或检查不通过的结果。
- 模型步数、工具调用数和无效动作数均能终止。

### 端到端测试

- 使用 Scripted Mock 覆盖五类验收场景。
- 固定随机性和估时参数，保证可复现。
- 实际输出和 Trace 保存到 `examples/`。

### 真实模型测试

- 有密钥时至少执行两条动态路径。
- 重点观察改变检索结果或时长结果后，模型下一动作是否变化。
- 不把真实模型测试放入默认离线 CI。

## 19. 错误处理与 CLI 退出码

初步约定：

- `0`：`completed` 或 `needs_input`，应用正常执行并给出业务结果。
- `2`：输入 JSON 或 CLI 参数无效。
- `3`：`incomplete`，达到执行预算。
- `4`：`failed`，任务执行失败。
- `5`：未处理的内部错误。

无论退出码为何，只要应用已启动，都尽可能输出结构化结果和 Trace 路径。

## 20. 安全与隐私

- `.env.example` 只列变量名，不包含真实密钥。
- 输入、输出和 Trace 不包含真实隐私数据。
- Trace 对模型请求只保存摘要，不保存认证头或环境变量。
- 工具注册表使用白名单，不允许模型提供任意模块名、文件路径或命令。
- 本项目工具不执行 Shell、不访问任意 URL。

## 21. 实现顺序约束

工程骨架阶段只建立模块、类型和可导入入口；核心 ReAct 阶段才实现图循环和动态路径。验收数据、示例、最终文档与全量验证按用户指定阶段顺序推进，不提前混做。

## 22. 本阶段待确认事项

本设计默认：

- 缺少业务必填字段时由模型根据缺失观察选择 `request_input`。
- 非法类型和负时长在进入图之前拒绝。
- 产品事实通过素材 ID 与事实 ID 双重追溯。
- 默认预算为 10 次模型决策、8 次工具调用、2 次无效动作。
- 正常完成必须同时通过当前脚本版本的时长检查和规则检查。

这些约定在确认后作为后续实现基线；若实现阶段发现技术冲突，需要先汇报再修改设计。

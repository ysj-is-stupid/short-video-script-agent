# 阶段 8：审计问题整改

## 整改原则

本阶段当时按照审计严重程度依次处理并逐项验证；后续用户已授权连续完成第二轮整改，详见阶段 9。

## 整改顺序

1. 事实依据约束：阻止非数字类产品事实扩写。
2. 模型输出错误分类：区分传输错误与 JSON/Schema 无效动作。
3. 最终方案文档同步：补充 DeepSeek Chat Completions 实现。
4. CLI 内部错误：实现结构化退出码 5。
5. GitHub 交付：题号、远程 URL、最终 commit 和 SHA。

## 第 1 项：事实依据约束

- 状态：已完成并纳入后续全量验证
- 触发原因：P01 只有“支持字幕”，真实完成稿却出现“字幕别再手打”“更省心”“简洁好用”，规则检查仍通过。
- 实际用时：约 20 分钟

### 设计

1. 保留现有素材 ID、事实 ID、数字和品牌词检查。
2. 对引用产品事实的分镜增加推断性宣传词检查。
3. 如果“自动、一键、无需手动、省时、省心、高效、好用”等表达没有出现在所引用事实原文中，返回 `unsupported_claim_language`。
4. 如果素材原文本身包含对应表达，则允许使用，避免把真实事实一律拦截。
5. 产品名或完整事实出现在无来源分镜时，返回 `product_claim_missing_source`。
6. 提示模型只能对素材事实做保守转述，不能从“支持功能”推导实现方式或业务效果。

### 边界

这是确定性的高风险表达拦截，不等同于完整语义蕴含模型。项目仍需在文档中披露开放世界事实核验限制，但必须确保当前真实完成稿中的明显扩写不能通过。

### 验收标准

- “支持字幕”允许通过。
- “字幕别再手打”“字幕处理更省心”“简洁好用”至少触发 `unsupported_claim_language`。
- 若未来素材明确写有相同能力或效果，对应表达可以通过。
- 真实模型最终完成稿不再包含 P01 无法证明的自动化、效率或易用性结论。
- 所有离线测试与示例仍保持通过。

## 后续整改项

第 5 项尚未开始，必须等待第 4 项完成并经用户确认。

## 第 4 项：CLI 内部错误结构化处理

- 状态：已完成并纳入后续全量验证
- 触发原因：详细设计约定未处理内部错误返回退出码 5 并尽可能输出结构化结果，但 CLI 只捕获已知输入和应用错误，其他异常会直接输出堆栈。
- 实际用时：约 10 分钟

### 设计

1. 已知配置、输入、文件和 JSON 错误继续返回退出码 2。
2. 未预期的 `Exception` 返回退出码 5 和 `internal_error`。
3. 错误消息只包含异常类型，不包含原始异常正文或参数值。
4. 提供 `--output` 时将错误写入输出 JSON，否则打印到标准输出。
5. 提供 `--trace` 时写入最小错误 Trace，包含模式、场景和清洗后的启动错误。
6. `KeyboardInterrupt` 等非 `Exception` 控制信号不被吞掉。

### 验收标准

- 注入带敏感正文的 `RuntimeError` 后退出码为 5。
- 输出和 Trace 文件均存在且为合法 JSON。
- 文件只包含 `RuntimeError` 类型，不包含异常正文。
- 已知输入错误仍返回 2。

### 实际结果

- 未预期 `Exception` 现在返回退出码 5 和 `internal_error`。
- 内部错误消息只包含异常类型，不包含原始异常正文。
- 提供 `--output` 时写出结构化错误 JSON。
- 提供 `--trace` 时写出最小错误 Trace，并在输出中引用该路径。
- Trace 或输出文件自身写入失败时，记录清洗后的写入异常类型并回退到标准输出。
- 已知配置、输入、文件和 JSON 错误继续返回退出码 2。
- `KeyboardInterrupt` 等控制信号不会被 `Exception` 捕获。
- 正常 `needs_input` CLI 路径复跑成功，退出码仍为 0。
- 干净环境 `pip check` 通过，完整 pytest 为 30 项通过。

## 第 3 项：最终方案文档同步

- 状态：已完成并纳入后续全量验证
- 触发原因：`docs/02-solution.md` 仍称所有真实模型都使用 OpenAI Responses API，但当前实现同时支持 OpenAI Responses 和 DeepSeek OpenAI 兼容 Chat Completions。
- 实际用时：约 5 分钟

### 更新范围

1. 说明 `LiveModelAdapter` 是供应商无关边界。
2. OpenAI 原生配置使用 `responses.parse` 和 Pydantic 结构化输出。
3. DeepSeek 配置使用 `chat.completions.create`、JSON Object 模式和二次 Pydantic 校验。
4. 说明变量识别、`.env` 自动加载和 Shell 环境优先级。
5. 说明传输错误与模型输出错误的不同处理。
6. 核对 README、最终方案、评估和 AI 使用说明的一致性。

### 验收标准

- 最终方案不再把 DeepSeek 描述为 Responses API。
- 文档描述与 `config.py`、`openai_adapter.py` 和 `graph.py` 一致。
- 文档不包含真实密钥、Base URL 值或模型值。

### 实际结果

- 最终方案已将 `LiveModelAdapter` 定义为供应商无关边界。
- OpenAI 原生路径明确为 `responses.parse`。
- DeepSeek 路径明确为 Chat Completions JSON Object 加本地 Pydantic 校验。
- 补充了供应商自动识别、变量名、`.env` 自动加载和 Shell 优先级。
- 补充 `model_request_error` 与 `decision_error` 的不同预算行为。
- README、最终方案、评估和 AI 使用说明之间未发现相互冲突的模型接入描述。
- Markdown 相对链接检查通过。
- 文档密钥值比较检查通过。

## 第 2 项：模型输出错误分类

- 状态：已完成并纳入后续全量验证
- 触发原因：DeepSeek JSON 内容在 `AgentDecision.model_validate_json` 校验失败时，会被宽泛的 `except Exception` 包装成可重试传输错误，导致 `invalid_decision_count` 不增加。
- 实际用时：约 10 分钟

### 设计

1. 新增 `ModelOutputValidationError`，表示模型已经返回内容，但内容不是合法 `AgentDecision`。
2. API 连接失败、超时、限流和服务端 5xx 继续使用 `ModelAdapterError`。
3. 4xx 中除 408、409、429 外默认视为不可重试配置或请求错误。
4. JSON/Pydantic 校验失败不保存原始响应正文，只记录清洗后的错误摘要。
5. 图将 `ModelOutputValidationError` 计入无效动作预算；达到上限后返回 `failed/model_output_invalid`。
6. 保留模型总步数上限，持续传输错误最终返回明确 `incomplete`。

### 验收标准

- 非法 JSON 由适配器抛出 `ModelOutputValidationError`。
- 连续两次非法输出后状态为 `failed/model_output_invalid`。
- `invalid_decision_count` 等于 2。
- 可重试传输错误恢复后仍能完成，且无效动作数保持 0。
- Trace 能区分 `model_request_error` 和 `decision_error`。

### 实际结果

- 新增 `ModelOutputValidationError`，专门表示已收到响应但 JSON/Schema 不合法。
- Pydantic `ValidationError` 转换为清洗后的输出校验错误，不保存原始正文。
- API 连接和超时错误保持可重试。
- HTTP 408、409、429 和 5xx 可重试；其他 HTTP 错误不可重试。
- 未预期的适配器异常变为不可重试内部错误。
- 图对 `ModelOutputValidationError` 增加无效动作计数并记录 `decision_error`。
- 连续两次非法输出实际得到 `failed/model_output_invalid`，计数为 2。
- 可重试传输错误恢复后仍完成，计数保持 0，Trace 类型为 `model_request_error`。
- 干净环境 `pip check` 通过，完整 pytest 为 28 项通过。

## 第 1 项实际结果

- 新增 `unsupported_claim_language`：推断性宣传词只有在引用事实原文明确包含时才允许。
- 新增 `product_claim_missing_source`：产品名或完整事实出现在无来源分镜时拒绝。
- 真实模型提示明确禁止从“支持功能”推导自动化、免手动、效率和易用性。
- 工具测试覆盖无依据非数字表达拒绝，以及素材明确支持时允许通过。
- 真实完成稿由 15.5 秒旧版本替换为 13.2 秒整改版本。
- 整改后的真实文案仅保留“云帧剪辑支持字幕”等可由 P01 证明的表达。
- 五组 Mock 示例已按新规则重新生成。
- 完整 pytest：26 项通过。

## 第 1 项边界

该实现是保守的高风险词与来源约束，不能替代通用自然语言蕴含模型。开放世界语义核验仍作为已知限制保留，但审计发现的明显自动化、效率和易用性扩写已经不能通过完成守卫。

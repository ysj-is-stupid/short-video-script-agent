# 03 评估结果

## 评估方法

十二组离线场景和两组历史真实模型场景均通过 CLI 实际运行，使用相同 LangGraph、工具、完成守卫和预算。Mock 记录证明确定性流程与状态转换；真实记录用于观察模型根据工具结果选择动作。

## 场景 01：正常生成与时长修正

文件：[输入](../examples/01-normal-duration-revision/input.json)、[输出](../examples/01-normal-duration-revision/output.json)、[Trace](../examples/01-normal-duration-revision/trace.json)。

实际结果：检索命中 P01；revision 1 估时 38.1 秒并被拒绝；下一动作提交 revision 2 再次估时为 28.0 秒；规则通过后状态为 `completed/all_checks_passed`。输出含三个分镜、P01 与 P01-F01，不含“效率提升80%”。

结论：通过。

## 场景 02：缺少关键信息

文件：[输入](../examples/02-missing-information/input.json)、[输出](../examples/02-missing-information/output.json)、[Trace](../examples/02-missing-information/trace.json)。

实际结果：动作只有 `request_input`；状态为 `needs_input/missing_required_fields`；请求字段为 `audience`；未调用业务工具。

结论：通过。

## 场景 03：无素材

文件：[输入](../examples/03-no-materials/input.json)、[输出](../examples/03-no-materials/output.json)、[Trace](../examples/03-no-materials/trace.json)。

实际结果：首次 `empty` 后使用不同查询再次检索；第二次仍为空后选择 `request_input`；状态为 `needs_input/no_supporting_materials`；没有生成产品脚本。

结论：通过。

## 场景 04：工具失败

文件：[输入](../examples/04-tool-failure/input.json)、[输出](../examples/04-tool-failure/output.json)、[Trace](../examples/04-tool-failure/trace.json)。

实际结果：两次检索均为 `error` 而非 `empty`；第一次错误后重试，第二次错误后选择 `fail`；状态为 `failed/tool_unavailable`，CLI 退出码为 4。

结论：通过。

## 场景 05：无依据事实修正

文件：[输入](../examples/05-unsupported-claim-revision/input.json)、[输出](../examples/05-unsupported-claim-revision/output.json)、[Trace](../examples/05-unsupported-claim-revision/trace.json)。

实际结果：首次规则结果为 `rejected`，摘要包含 `unsupported_numeric_claim`；下一动作删除无依据内容并重新估时；再次规则检查通过；最终输出不含 `80%`。

结论：通过。

## 动态路径差异

时长路径观察为 `rejected`，后续动作是提交新稿并重新估时。无素材路径观察为 `empty`，后续先改写查询再请求补充。工具失败路径观察为 `error`，后续先重试再明确失败。

## 场景 06—12：失败、预算和输入边界

- [06 时长工具超时](../examples/06-duration-timeout/trace.json)：`estimate_duration` 返回 `timeout`，模型选择失败，最终为 `failed/tool_timeout`。
- [07 规则工具失败](../examples/07-rule-tool-failure/trace.json)：时长通过后 `check_rules` 返回 `error`，最终为 `failed/tool_unavailable`。
- [08 模型步数上限](../examples/08-model-step-limit/trace.json)：达到上限后为 `incomplete/model_step_limit_reached`，没有伪装成功。
- [09 工具调用上限](../examples/09-tool-call-limit/trace.json)：达到上限后为 `incomplete/tool_call_limit_reached`。
- [10 多字段缺失](../examples/10-multiple-missing-fields/output.json)：一次返回 `audience`、`platform`、`style` 三个机器字段标识及自然语言详情。
- [11 非法字段类型](../examples/11-invalid-input-type/trace.json)：字符串时长在进入图前被 Schema 拒绝，CLI 退出码为 2，并保留结构化启动错误记录。
- [12 工具未预期异常](../examples/12-unexpected-tool-exception/trace.json)：执行节点捕获异常并转为清洗后的工具错误，最终明确失败。

## 真实模型路径 01：正常完成

文件：[输入](../examples/live-01-normal/input.json)、[输出](../examples/live-01-normal/output.json)、[Trace](../examples/live-01-normal/trace.json)。

实际动作是 `search_materials → estimate_duration → check_rules → finish`。整改后的最终状态为 `completed/all_checks_passed`，估时 13.2 秒，引用 P01，规则检查通过。文案只保留“支持字幕”及保守引导，不再包含“别再手打”“省心”“好用”等素材无法证明的推断。真实模型首稿已经低于 30 秒，因此该路径没有触发压缩；超时修正由离线确定性场景覆盖。

该历史 Trace 的 provider 可由当次运行记录确认为 DeepSeek，但当时没有采集模型名、SDK 版本和响应 ID。迁移到 Trace Schema 2.0 后这些字段保持空值并标记 `historical_run_metadata_not_captured`，没有使用当前 `.env` 补写或伪造历史证据。新 live 运行会自动记录完整的非秘密元数据。

## 真实模型路径 02：无素材

文件：[输入](../examples/live-02-no-materials/input.json)、[输出](../examples/live-02-no-materials/output.json)、[Trace](../examples/live-02-no-materials/trace.json)。

实际动作是 `search_materials → search_materials → request_input`。两次查询不同且结果均为 `empty`，最终为 `needs_input/no_supporting_materials`，没有生成标题或脚本。

原历史输出把三句自然语言放入 `requested_fields`。Schema 整改后保存格式迁移为机器字段 `product_materials`，原信息合并保留在 `requested_details`；该迁移不改变当次模型动作、检索结果或终止状态。

## 真实接口稳定性观察

第一次完整尝试中出现 HTTP 500 和 522。原实现错误地把可重试传输错误累计为无效动作，导致 `model_output_invalid`。修正后，传输错误只消耗模型步数，真正违反动作契约才增加无效动作数；持续传输失败最终由模型步数上限结束。随后两条真实路径均成功产生有效结果。

## 自动测试

从此前不存在的 `.validation-final-20261107` 创建全新隔离环境并安装 `requirements.txt` 后，`pip check` 无损坏依赖，48 项测试全部通过。最新静态检查结果见 [test-results.txt](../examples/test-results.txt)。

## 限制

- 真实模型只有两条样本，不能代表稳定性分布或生产质量。
- 时长为算法估算，真人语速和停顿可能不同。
- 关键词检索支持声明式产品别名，但不处理未声明的复杂同义词。
- 规则检查区分步骤编号与效果数字并采用短语正则，但不能完全验证自由文本语义蕴含。
- 合成数据规模小，只覆盖项目要求路径。


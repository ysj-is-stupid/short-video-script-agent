# 验收示例

所有正式示例均使用 `model_mode=mock` 实际运行生成。Mock 证明流程与状态转换，不证明真实模型决策效果。

公共参数：

```powershell
$common = @(
  "--materials", "data/materials.json",
  "--rules", "data/brand_rules.json",
  "--model-mode", "mock"
)
```

## 01 正常生成与时长修正

```powershell
python -m short_video_agent run `
  --input examples/01-normal-duration-revision/input.json @common `
  --scenario duration_revision `
  --output examples/01-normal-duration-revision/output.reproduced.json `
  --trace examples/01-normal-duration-revision/trace.reproduced.json
```

实际记录：[输入](01-normal-duration-revision/input.json)、[输出](01-normal-duration-revision/output.json)、[Trace](01-normal-duration-revision/trace.json)。

## 02 缺少关键信息

```powershell
python -m short_video_agent run `
  --input examples/02-missing-information/input.json @common `
  --scenario missing_information `
  --output examples/02-missing-information/output.reproduced.json `
  --trace examples/02-missing-information/trace.reproduced.json
```

实际记录：[输入](02-missing-information/input.json)、[输出](02-missing-information/output.json)、[Trace](02-missing-information/trace.json)。

## 03 无素材

```powershell
python -m short_video_agent run `
  --input examples/03-no-materials/input.json @common `
  --scenario query_rewrite `
  --output examples/03-no-materials/output.reproduced.json `
  --trace examples/03-no-materials/trace.reproduced.json
```

实际记录：[输入](03-no-materials/input.json)、[输出](03-no-materials/output.json)、[Trace](03-no-materials/trace.json)。

## 04 工具失败

```powershell
python -m short_video_agent run `
  --input examples/04-tool-failure/input.json @common `
  --scenario tool_failure `
  --simulate-search-failures 2 `
  --output examples/04-tool-failure/output.reproduced.json `
  --trace examples/04-tool-failure/trace.reproduced.json

$LASTEXITCODE  # 预期为 4
```

实际记录：[输入](04-tool-failure/input.json)、[输出](04-tool-failure/output.json)、[Trace](04-tool-failure/trace.json)。

## 05 无依据事实修正

```powershell
python -m short_video_agent run `
  --input examples/05-unsupported-claim-revision/input.json @common `
  --scenario unsupported_claim_revision `
  --output examples/05-unsupported-claim-revision/output.reproduced.json `
  --trace examples/05-unsupported-claim-revision/trace.reproduced.json
```

实际记录：[输入](05-unsupported-claim-revision/input.json)、[输出](05-unsupported-claim-revision/output.json)、[Trace](05-unsupported-claim-revision/trace.json)。

## 06 时长工具超时

```powershell
python -m short_video_agent run --input examples/06-duration-timeout/input.json @common `
  --simulate-duration-fault timeout `
  --output examples/06-duration-timeout/output.reproduced.json `
  --trace examples/06-duration-timeout/trace.reproduced.json
# 预期退出码 4，failed/tool_timeout
```

## 07 规则工具失败

```powershell
python -m short_video_agent run --input examples/07-rule-tool-failure/input.json @common `
  --simulate-rule-fault error `
  --output examples/07-rule-tool-failure/output.reproduced.json `
  --trace examples/07-rule-tool-failure/trace.reproduced.json
# 预期退出码 4，failed/tool_unavailable
```

## 08—09 执行预算上限

```powershell
python -m short_video_agent run --input examples/08-model-step-limit/input.json @common `
  --max-model-steps 1 `
  --output examples/08-model-step-limit/output.reproduced.json `
  --trace examples/08-model-step-limit/trace.reproduced.json

python -m short_video_agent run --input examples/09-tool-call-limit/input.json @common `
  --max-tool-calls 1 `
  --output examples/09-tool-call-limit/output.reproduced.json `
  --trace examples/09-tool-call-limit/trace.reproduced.json
# 两条命令预期退出码均为 3，状态为 incomplete
```

## 10—12 输入和执行兜底

```powershell
python -m short_video_agent run --input examples/10-multiple-missing-fields/input.json @common `
  --output examples/10-multiple-missing-fields/output.reproduced.json `
  --trace examples/10-multiple-missing-fields/trace.reproduced.json

python -m short_video_agent run --input examples/11-invalid-input-type/input.json @common `
  --output examples/11-invalid-input-type/output.reproduced.json `
  --trace examples/11-invalid-input-type/trace.reproduced.json

python -m short_video_agent run --input examples/12-unexpected-tool-exception/input.json @common `
  --simulate-duration-fault exception `
  --output examples/12-unexpected-tool-exception/output.reproduced.json `
  --trace examples/12-unexpected-tool-exception/trace.reproduced.json
```

## 真实模型记录

以下记录使用本地 `.env` 中的 DeepSeek 兼容配置实际生成，仓库没有保存密钥或 Base URL 值。

两条记录生成时使用旧版 Trace，未采集模型名、SDK 版本和响应 ID。当前文件已迁移为 Trace Schema 2.0，并明确标记 `historical_run_metadata_not_captured`；空缺字段没有用当前配置推测补写。轮换新 Key 后可用下列命令生成带完整元数据的新记录。

### Live 01 正常完成

```powershell
python -m short_video_agent run `
  --input examples/live-01-normal/input.json `
  --materials data/materials.json `
  --rules data/brand_rules.json `
  --model-mode live `
  --output examples/live-01-normal/output.reproduced.json `
  --trace examples/live-01-normal/trace.reproduced.json
```

实际记录：[输入](live-01-normal/input.json)、[输出](live-01-normal/output.json)、[Trace](live-01-normal/trace.json)。

### Live 02 无素材

```powershell
python -m short_video_agent run `
  --input examples/live-02-no-materials/input.json `
  --materials data/materials.json `
  --rules data/brand_rules.json `
  --model-mode live `
  --output examples/live-02-no-materials/output.reproduced.json `
  --trace examples/live-02-no-materials/trace.reproduced.json
```

实际记录：[输入](live-02-no-materials/input.json)、[输出](live-02-no-materials/output.json)、[Trace](live-02-no-materials/trace.json)。

最终验证摘要见 [test-results.txt](test-results.txt)。


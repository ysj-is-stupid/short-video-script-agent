# 短视频脚本 Agent

## 提交信息

- 题号/题目：短视频脚本 Agent（原始题面未提供数字编号）
- GitHub：[ysj-is-stupid/short-video-script-agent](https://github.com/ysj-is-stupid/short-video-script-agent)
- 默认分支：`main`
- 最终 commit SHA：以提交材料中附带的 `main` 最新 SHA 为准。

这是一个基于 LangGraph 的短视频脚本 Agent。它根据主题、受众、平台、目标时长和风格检索产品素材，生成带来源的分镜脚本，并通过时长估算和品牌规则检查反复修订。

核心链路不是固定条件流程：模型适配器每次读取最新工具观察，再选择检索、重新检索、估时、规则检查、请求补充、失败或完成。

## 评审快速入口

建议按以下顺序查看：

1. [需求与成功标准](docs/01-requirements.md)
2. [方案与动态决策](docs/02-solution.md)
3. [实际评估结果](docs/03-evaluation.md)
4. [正常时长修正 Trace](examples/01-normal-duration-revision/trace.json)
5. [无素材 Trace](examples/03-no-materials/trace.json)
6. [工具失败 Trace](examples/04-tool-failure/trace.json)
7. [无依据事实修正 Trace](examples/05-unsupported-claim-revision/trace.json)
8. [真实模型正常路径 Trace](examples/live-01-normal/trace.json)
9. [真实模型无素材路径 Trace](examples/live-02-no-materials/trace.json)
10. [最终测试结果](examples/test-results.txt)
11. [时长工具超时 Trace](examples/06-duration-timeout/trace.json)
12. [规则工具失败 Trace](examples/07-rule-tool-failure/trace.json)
13. [模型步数上限 Trace](examples/08-model-step-limit/trace.json)
14. [工具调用上限 Trace](examples/09-tool-call-limit/trace.json)

## 环境

- Python 3.11 或更高版本；开发环境使用 Python 3.13.9。
- LangGraph 1.2.20。
- Pydantic 2.12.4。
- OpenAI Python SDK 2.54.0。
- pytest 8.4.2。

## 安装

```powershell
git clone <repository-url>
cd <repository-directory>
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

当前工作区遗留的 `.venv` 含损坏的 `pydantic_core` 原生扩展，不是权威验证环境。评审应删除或避开旧目录并创建全新的虚拟环境，例如使用 `.venv-review`；不要以旧 `.venv` 的失败判定项目依赖不可安装。

仓库同时包含已校验的 `uv.lock`；使用 uv 时可运行 `uv sync --extra dev`。

离线 Mock 不需要任何环境变量或密钥。

程序会自动加载仓库根目录下被 Git 忽略的 `.env`，但即使文件中存在完整凭据，默认仍为 `mock`，不会联网。OpenAI 原生配置为：

```powershell
$env:MODEL_MODE = "live"
$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "your-model-name"
```

也支持 DeepSeek 的 OpenAI 兼容接口：

```dotenv
DEEPSEEK_API_KEY=your-api-key
DEEPSEEK_BASE_URL=your-base-url
DEEPSEEK_MODEL=your-model-name
```

只有显式设置 `MODEL_MODE=live` 或在 CLI 传入 `--model-mode live` 才会联网。DeepSeek 配置只负责选择供应商和连接参数，不会自行开启 live。Shell 环境变量优先于 `.env`。

不要把真实密钥写入仓库或 `.env.example`。`.gitignore` 只能防止普通 `git add`，不能防止强制添加、目录压缩、聊天粘贴、日志输出或其他复制方式泄漏 `.env`；提交或打包前必须单独检查。任何曾暴露的密钥都应在供应商后台作废并轮换。

## 运行正常场景

```powershell
python -m short_video_agent run `
  --input examples/01-normal-duration-revision/input.json `
  --materials data/materials.json `
  --rules data/brand_rules.json `
  --model-mode mock `
  --scenario duration_revision `
  --output examples/01-normal-duration-revision/output.reproduced.json `
  --trace examples/01-normal-duration-revision/trace.reproduced.json
```

预期结果：首稿估时 38.1 秒，模型根据观察提交 revision 2，重新估时 28.0 秒，规则检查通过后完成。

## 运行其他验收场景

完整命令见 [examples/README.md](examples/README.md)。其中工具失败场景预期返回退出码 `4`，但仍会写出结构化输出和 Trace。

## 真实模型入口

配置环境变量后，将正常命令中的参数改为：

```powershell
--model-mode live
```

`--scenario` 在真实模式中被忽略。真实模型和 Mock 共用 `AgentDecision`、LangGraph、工具、完成守卫和执行预算。

仓库包含两条真实 DeepSeek 兼容接口运行记录：正常完成路径和无素材路径。Mock Trace 仍只用于证明确定性流程和状态转换，不能替代真实模型效果评估。

## 测试

```powershell
python -m pytest -q
```

测试覆盖数据契约、三项工具、动态路径、完成守卫、模型与工具预算、传输错误分类、OpenAI Responses 与 DeepSeek Chat Completions 适配边界、模型输出 Schema 错误、事实扩写、CLI 错误输出、Trace 以及提交示例。最新通过数量见 `examples/test-results.txt`。

## 输入

请求 JSON 支持主题、受众、平台、目标时长、风格、产品名、素材范围和品牌规则范围。

缺少业务必填字段不会被自动猜测，而是作为观察交给模型选择 `request_input`。`requested_fields` 只使用固定机器字段标识，面向用户的说明位于 `requested_details`。负时长或错误类型会在进入图之前拒绝。

## 输出

`AgentResult` 包含标题、分镜、旁白或字幕、分镜及总预计时长、素材和事实 ID、检查报告、风险、任务状态、终止原因和 Trace 路径。

任务状态包括 `completed`、`needs_input`、`incomplete` 和 `failed`。

CLI 退出码：

- `0`：完成或正常请求补充信息。
- `2`：配置、输入、文件或 JSON 错误。
- `3`：达到模型步数或工具调用预算，任务未完成。
- `4`：业务任务明确失败。
- `5`：未预期的内部错误；输出只包含清洗后的异常类型。

提供 `--output` 和 `--trace` 时，错误路径也会尽可能写出结构化 JSON。

## Trace

每个 Trace 同时包含：

- `review_steps`：步骤、模型提议参数、规范化后的实际执行参数、返回摘要、后续动作、简要决策依据和脚本修订号。
- `raw_events`：LangGraph 节点级事件。
- `model_mode`：`mock` 或 `live`。
- `model_metadata`：provider、模型名、SDK/应用版本、可用响应 ID 和元数据采集状态，不含密钥或 Base URL。
- `mock_boundary`：离线模式的证据边界。

Trace 不保存密钥，也不要求或记录模型内部思维过程。

## 项目结构

```text
src/short_video_agent/   Agent、模型适配器、工具和 CLI
tests/                   可执行测试
examples/                核心、失败、预算和边界输入、实际输出及 Trace
data/                    合成产品素材和品牌规则
docs/                    规定的需求、方案、评估、AI 使用和复盘文档
docs/design/             各阶段设计与实施记录
```

## 已知限制

- 时长为固定语速算法估算，不能替代真人试读。
- 本地素材检索是确定性关键词检索，支持显式产品别名，但不是语义向量检索。
- 规则工具能确定性检查引用、效果数字和品牌词，并过滤步骤编号；短语规则仍不能完成开放世界事实核验。
- 当前只有两条真实模型路径，尚不足以统计模型稳定性和质量分布。
- 两条历史 live Trace 在最初运行时未采集模型名、SDK 版本和响应 ID，已明确标记 `historical_run_metadata_not_captured`；不会用当前配置伪造历史信息。新运行会自动采集这些字段。
- 当前不把明显低于目标时长视为硬失败，但低于目标 70% 时会在 `risks` 中提示。
- 未实现界面、部署、外部知识库或生产级持久化。

## 实际用时与未完成项

第一轮实现用时约 2 小时 47 分钟；第二轮审计整改日历历时约 3 小时 03 分钟（包含交互等待），累计记录历时约 5 小时 50 分钟，超过建议的 3 小时。仓库内整改及公开 GitHub 上传已完成；原始题面未提供数字题号。已暴露 Key 的作废轮换仍需用户在供应商后台完成。


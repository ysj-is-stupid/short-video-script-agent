# 阶段 7：全量验证

## 阶段状态

- 状态：已完成；第二轮审计整改另见阶段 9
- 目标：验证离线与真实模型入口、全部验收材料、测试、文档和敏感信息边界
- 实际用时：约 40 分钟

## 用户提供的模型配置

本地 `.env` 使用以下变量名：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`

记录只包含变量名，不包含值。`.env` 已被 Git 忽略。

## 兼容改造

1. 将应用配置改为供应商无关的 `model_api_key`、`model_name`、`model_base_url` 和 `model_provider`。
2. 保留原有 `OPENAI_API_KEY`、`OPENAI_MODEL` 和可选 `OPENAI_BASE_URL` 兼容入口。
3. 当时的实现会在检测到完整 DeepSeek 配置且未显式设置 `MODEL_MODE` 时选择 `live`；第二轮审计已确认该行为存在误联网风险，并在阶段 9 批次 1 改为显式启用 live。
4. DeepSeek 使用 OpenAI SDK 的兼容 Chat Completions 接口请求 JSON 对象，再由 Pydantic 校验为 `AgentDecision`。
5. OpenAI 原生配置继续使用 Responses API 结构化输出。

## 验证步骤

1. 配置检查：只报告变量是否存在，不输出值。
2. 单次最小模型决策检查：验证兼容端点、模型和 JSON 输出。
3. 真实路径 A：正常素材、超时长修正与完成。
4. 真实路径 B：无素材后改写查询或请求补充。
5. 离线路径：重新生成五组 Mock 示例并核对。
6. 自动测试：编译检查和完整 pytest。
7. 文档检查：必需文件、相对链接、示例引用和运行命令。
8. 安全检查：密钥、`.env`、本机绝对路径和隐私数据。

## 真实模型验收标准

- 至少两条路径使用 `model_mode=live`。
- Trace 中不出现 API Key。
- 工具返回后确实出现新的模型动作。
- 正常路径通过当前脚本版本的时长和规则检查。
- 无素材路径不得生成无来源产品事实。
- 若模型或兼容接口不支持所需 JSON 契约，记录真实失败，不用 Mock 冒充。

## 最终输出

- `examples/test-results.txt`
- 成功时生成 `examples/live-*` 的输入、输出与 Trace。
- 更新 README、评估、AI 使用、复盘和本阶段记录。
- Git 工作区与交付缺口报告。

## GitHub 边界

本阶段当时用户尚未提供 GitHub 仓库 URL 或要求创建远程仓库，因此只完成本地验证和提交准备；用户随后明确授权创建公开仓库，最终交付结果见阶段 9。

## 实际结果

### 配置与兼容

- 成功识别 DeepSeek 三个自定义变量名，未输出其值。
- 配置重构为供应商无关字段。
- `.env` 自动加载，Shell 变量优先，`.env` 被 Git 忽略；这是当次验证事实，不代表忽略规则能够防止打包或强制添加泄漏。
- DeepSeek 兼容 Chat Completions JSON 最小调用成功。

### 真实模型路径

1. 正常路径：`search_materials → estimate_duration → check_rules → finish`；事实约束整改后最终完成，13.2 秒，引用 P01，未包含推断性宣传。
2. 无素材路径：`search_materials(empty) → 改写查询再次 search_materials(empty) → request_input`，未生成脚本。

初次完整运行观察到 HTTP 500 和 522。修复了传输错误被累计为无效动作的问题；传输错误现在消耗模型预算但不污染动作校验计数。

### 离线与自动测试

- 五组 Mock 场景全部重跑，预期退出码为 0/0/0/4/0。
- 全新隔离环境从头安装依赖成功。
- `pip check`：无损坏依赖。
- pytest：CLI 内部错误整改后 30 项通过，包括传输错误、Schema 无效动作、非数字推断性宣传、结构化退出码和真实输出回归测试。
- Python 编译检查通过。
- `uv lock --check`：通过，锁文件与 `pyproject.toml` 一致。

### 静态交付检查

- JSON：通过。
- Markdown 相对链接：通过。
- 当次候选工作区文件与本地密钥值比较：通过；由于当时仓库没有提交，该结果不应表述为 committed-secret 检查。
- 本机绝对路径扫描：通过。
- `.env` Git 忽略检查：通过。

### 宿主环境说明

全局 Conda 环境存在与本项目无关的 numba/numpy 冲突。旧 `.venv` 也包含不兼容二进制包，因此没有清空或覆盖它；另建此前不存在的 `.validation-venv-20261107` 完成权威隔离验证，该目录被 Git 忽略。

## 尚未完成

- 本阶段当时尚未配置 GitHub 远程仓库；后续已完成。
- 本阶段当时尚未创建最终 Git 提交和 commit SHA；后续已完成。

# 阶段 4：工程骨架

## 阶段状态

- 状态：已完成并通过后续全量验证
- 目标：建立可安装、可导入、可测试的工程结构，为核心 ReAct 链路提供稳定契约
- 实际用时：约 12 分钟

## 本阶段范围

1. 初始化本地 Git 仓库。
2. 建立 `src/`、`tests/`、`examples/`、`data/` 和 `docs/` 目录。
3. 配置 Python 包、依赖、pytest、环境变量示例和 Git 忽略规则。
4. 实现详细设计中确定的 Pydantic 数据契约。
5. 定义 LangGraph 状态类型、应用配置和错误类型。
6. 定义模型适配器与工具的接口边界。
7. 建立 CLI 和 `python -m` 入口，支持版本与帮助信息。
8. 使用最小测试证明骨架可导入且基础校验有效。

## 明确不在本阶段实现

- LangGraph 节点、边和循环。
- 真实模型调用与 Scripted Mock 场景决策。
- 素材检索、时长估算、规则检查逻辑。
- 完成守卫和执行预算运行逻辑。
- 五类验收场景、实际输出、Trace 和最终文档。

## 骨架验收标准

- `python -m short_video_agent --version` 可以执行。
- `python -m short_video_agent --help` 可以执行。
- 包内模块可导入。
- 业务缺失字段可进入数据模型并被识别，而非法时长会被拒绝。
- 环境配置不读取或提交真实密钥。
- 最小 pytest 测试全部通过。

## 计划文件

```text
.env.example
.gitignore
README.md
pyproject.toml
requirements.txt
src/short_video_agent/
  __init__.py
  __main__.py
  cli.py
  config.py
  errors.py
  schemas.py
  state.py
  graph.py
  trace.py
  model/
  tools/
tests/test_skeleton.py
examples/.gitkeep
data/.gitkeep
```

`graph.py`、模型实现和工具实现只保留清晰接口或待实现边界，不提供会被误认为已经完成核心链路的伪实现。

## 实际完成结果

- 已初始化本地 Git 仓库，当前尚未创建提交或远程仓库。
- 已建立 Python `src` 布局、包元数据、依赖与 pytest 配置。
- 已提供 `.env.example`，默认使用无需密钥的 `mock` 模式。
- 已实现请求、素材、规则、脚本、动作、工具结果、Trace 和最终结果的数据契约。
- 已实现 LangGraph `AgentState` 类型及追加式字段 Reducer 声明。
- 已实现环境配置、稳定错误码基类、模型协议、工具协议和白名单注册表。
- 已建立 CLI 模块入口；当前只提供帮助与版本，避免伪装成已完成的 Agent。
- 已加入 6 个骨架测试。
- 已为 `data/` 和 `examples/` 写入用途说明，但尚未加入验收数据。

## 验证记录

执行命令：

```powershell
python -m pip install -e . --no-deps
python -m short_video_agent --version
python -m short_video_agent --help
python -m pytest
```

实际结果：

- editable 安装成功。
- 版本命令输出 `short-video-agent 0.1.0`。
- CLI 帮助正常显示。
- pytest：`6 passed in 0.04s`。

## 骨架测试覆盖

1. 包版本可读取。
2. 缺少业务信息时字段保留给后续 Agent 路径处理。
3. 空白业务文本被识别为缺失。
4. 负时长在进入图之前被拒绝。
5. 默认配置为离线模式且预算明确。
6. 工具注册表初始为空。

## 阶段边界复核

本阶段没有实现 LangGraph 图、模型决策、三个业务工具、完成守卫、Trace 持久化或验收场景。`graph.py`、`OpenAIModelAdapter` 和 `ScriptedMockAdapter` 明确抛出 `NotImplementedError`，防止骨架被误认为已经满足核心 ReAct 要求。

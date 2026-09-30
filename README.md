<div align="center">

# LLM API Tester

### 给一堆中转站做体检：通不通、快不快、有没有偷偷换模型。

Windows 桌面工具。管理多个 LLM 供应商（Base URL + API Key + 协议），一键测**连通**与**延迟**、
拉**模型列表**、测**首字延迟（TTFT）**，并展示每个模型的**模态 / 上下文长度 / 思考档位**。

[![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white)]()
[![PySide6](https://img.shields.io/badge/UI-PySide6-2C6E93?logo=qt&logoColor=white)]()

[解决什么问题](#解决什么问题) · [功能](#功能) · [TTFT 口径](#ttft-口径是怎么定义的) · [模型一致性检测](#模型一致性检测) · [运行](#运行)

</div>

---

## 解决什么问题

手上一堆 OpenAI 兼容的中转站 / 网关 / 本地服务时，真正花时间的是这几件事：

- **这个 URL 到底通不通？** 光 ping 端口没用——端口开着不代表 `/v1/models` 能返回。
- **慢在哪？** 是握手慢、首字节慢，还是模型本身 Thinking 慢？
- **它到底给我什么模型？** 中转站最常见的猫腻：请求 `gpt-4o` 实际路由到别的模型。
- **这个模型支持什么？** 能不能带图？上下文多长？有没有思考档位？

> **不是聊天客户端。** 不做对话、不做 Prompt 市场。它只回答上面这四个问题。

## 功能

### 多供应商管理

每个供应商 = 显示名称 + Base URL + API Key + 协议。协议支持：

| 协议 | 说明 |
|---|---|
| **OpenAI Compatible** | 自动补 `/v1`，最通用的一类 |
| **Anthropic Messages** | 不乱补路径，内部依次试 `/v1/...` |
| **Gemini** | Key 走 query 参数而非 header |
| **Zhipu / Z.AI v4** | 智谱系 |

> Key 留空则**不发送鉴权头**——方便直接测 Ollama / vLLM 等本地服务。

### 连通与延迟

「测试连接」是**真的去打模型列表接口**（不是 ping TCP），返回 HTTP 状态码 + 耗时毫秒。
失败会区分：可达但无模型列表、鉴权失败、限流、服务端错误、超时、网络错误、TLS 错误、JSON 解析失败。

顶栏可一键测所有**已启用**供应商，测完汇总成功 / 失败条数与平均延迟。

### TTFT 批量测速

单模型 ⚡ 按钮，或顶栏「测当前全部首字」逐行刷新。并发 1–8 可调（默认 3），可随时取消，
失败不中断后面的行。批量与单行在同一供应商内**互斥**，不会抢着跑。

### 模型徽章

`T` 文本 · `图` 图像输入 · `听` · `视` · 上下文 `1M` / `204800` · `想` 思考档位（悬停看具体档位）。

数据来源按优先级**只补空、不瞎覆盖**：

1. 接口返回字段 → 2. 内置对照表（精确 id，再最长前缀）→ 3. 名字启发式（`vl`/`vision` → 图）

> **未知模型只标 `T`，不编造思考档。** 对照表在 `app/catalog.py`，直接改即可。

### 测速历史

每次测速都保存该模型的最新结果，并在当前供应商下保留**最近 500 条无 Key 历史**（随配置持久化，重启不丢）。
历史面板内含条形图（各模型平均首字）、折线图（单模型趋势）与明细表，可筛选、可导出 CSV、可清空。

### 其他

- **Key 安全**：本地保存用 **Windows DPAPI** 加密（按当前用户绑定），配置文件不存明文。日志不含任何 Key 与鉴权头。
- **Key 拖放**：按住「拖动」可直接拖到记事本 / 浏览器 / Cherry Studio 的输入框（标准 OLE 文本拖放）。
- **外观**：浅色纸感 / 深色灰黑 / 跟随系统，实时切换。

## TTFT 口径是怎么定义的

大多数测速工具在这一步糊弄过去，这个项目把它写死了：

- **主指标 = 发出流式请求 → 第一条非空文本**，毫秒。TTFB 仅作参考，**不冒充 TTFT**。
- 空串、只有 `role` 没有正文的 chunk **不算**首字。
- 思考字段（`reasoning_content`、Anthropic `thinking`、Gemini `thought`）**算**首字，结果标注来源。
- 流结束仍无文本 → 记失败 `no_content`，不标成功。
- **拿到首字立即断流**，省 token。
- 默认 `max_tokens=8`（可在设置调整），该值会写进测速结果，便于复现与比较。
- 默认关闭思考再测；服务端不认就自动去掉该参数重试并标注。强制思考模型标「首字来自思考字段 / 疑似强制思考」，**不当故障**。

> 重思考模型（如 glm-4.5）在默认 10s 超时内可能出不来首字，会记超时——这是按需求拍板的口径。
> 想要慢模型的数据就把超时调大。

## 模型一致性检测

**这是本项目最实际的一个功能。**

测速时从流式响应里读「上游实际使用的模型」：OpenAI 格式取 chunk 的 `model`，
Anthropic 取 `message_start` 的 `message.model`，Gemini 取 `modelVersion`。

与请求的模型 ID 比对：

| 情况 | 行为 |
|---|---|
| **不一致** | 首字结果标 `· 上游:xxx` 并显示**琥珀色警示** |
| 仅版本后缀差异（`glm-4.7:latest`、`models/` 前缀） | 只标注，不警示 |
| 上游没报告 | 不标注 |

悬停首字结果可看「请求 X · 上游返回 Y（判定）」明细；历史记录与导出 CSV 都带
`reported_model` / `model_match` 字段。

> 典型用途：识别中转站 / 网关悄悄把请求路由到别的模型。

## 技术栈与结构

Python 3.13 · PySide6 · httpx · PyInstaller 单文件打包。DPAPI 用 `ctypes` 直调，**无第三方依赖**。

```
main.py               入口（浅色调色板强制，深色系统模式下界面不花）
app/
  ui.py               主界面（1080 行，最大的一块）
  history_dialog.py   测速历史面板：图表 + 明细 + CSV
  tester.py           连通性 + TTFT 引擎（SSE 解析、400 去参重试、首字断流）
  taskman.py          后台 asyncio 线程 + Qt 信号（批量 / 并发 / 取消 / 互斥）
  net.py              httpx 客户端 / 错误归类 / URL 校验（仅 http/https）
  crypto_dpapi.py     DPAPI（ctypes）
  history.py          无 Key 测速历史记录与 CSV 导出
  catalog.py          模型徽章对照表 + 启发式
  config.py           %APPDATA% 持久化（Key DPAPI 加密）
  theme.py            浅色纸感 / 深色灰黑调色板
  models.py           Provider / ModelRow
  protocols/          四种协议适配（headers、模型路径、SSE 首字解析、关思考参数）
tests/
  smoke_offline.py    离线逻辑自检
  smoke_real.py       真实端点联调（Key 走环境变量）
  smoke_taskman.py    批量 + 取消管线冒烟
  ui_grab.py          离屏截图自检
tools/make_icon.py    重新生成应用图标
```

约 3900 行 Python（含测试）。

## 运行

```bash
# 源码运行
python main.py

# 打包（先重新生成图标，输出 dist\LLM-API-Tester.exe）
build.bat

# 单独重新生成图标
python tools/make_icon.py
```

首次打开会自动出现两个**空 Key 示例供应商**（OpenAI Compatible / Anthropic）和几条示例模型，
自己把 Key 填进去就能测。本机已有配置不会被覆盖。

> **发给别人：只发 `dist\LLM-API-Tester.exe`。** 不要发 `%APPDATA%\LLMApiTester\config.json`——
> 那里才有你自己的 Key。exe 里不含任何 Key。

## 注意事项

- exe 未签名，首次运行 SmartScreen 可能拦截：点「更多信息 → 仍要运行」。
- 测速会**真实调用模型**（prompt「回复一个字：好」，最大输出 Token 默认 8），可能产生少量费用。
- 全软件同一时刻只跑一个批量任务。
- 「跳过 TLS 校验」仅用于排查证书问题，**有中间人风险**。
- 「复制」「拖动」是用户主动操作，输出明文 Key；掩码状态下复制的也是真 Key。

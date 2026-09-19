# LLM API Tester

Windows 桌面工具：管理多个 LLM 供应商（Base URL + API Key + 协议），一键测连通/延迟、拉模型列表、测模型首字延迟（TTFT），并展示模型的模态、上下文长度、思考档位徽章。

技术栈：Python 3.13 + PySide6 + httpx，PyInstaller 打包单文件 exe。
需求说明见 `需求说明.md`。

## 运行

```bash
# 源码运行
python main.py

# 打包（先重新生成测速仪图标，输出 dist\LLM-API-Tester.exe）
build.bat

# 单独重新生成图标（assets\app.ico / app.png）
python tools/make_icon.py
```

**发给别人：只发 `dist\LLM-API-Tester.exe`。** 不要发 `%APPDATA%\LLMApiTester\config.json`，那里才有你自己的 Key。exe 里不含任何 Key。

对方第一次打开会自动出现两个**空 Key 示例供应商**（OpenAI Compatible / Anthropic）和几条示例模型，自己把 Key 填进去就能测。你本机已经有配置的话不会被覆盖。

## 功能对照

| 功能 | 位置 |
|------|------|
| 左侧供应商按名称正序 / 反序 | 左侧「↑ 正序」按钮，再点切反序 |
| 测当前供应商全部模型首字（逐行刷新、可取消、显示 3/12 进度） | 顶栏「测当前全部首字」 |
| 单模型测速 | 模型行 ⚡ 按钮 |
| 测试连接（真实请求模型列表接口，显示状态码+耗时） | 右侧「测试连接」 |
| 获取模型（手动添加的行不会被冲掉） | 右侧「获取模型」「添加模型」 |
| 保存最新测速结果、保留历史并导出 CSV | 模型列表「导出记录」 |
| 测速历史面板：软件内图表（各模型平均首字条形图 / 单模型趋势折线）+ 明细表，按供应商/模型筛选，可导出 CSV、可清空 | 顶栏「历史」 |
| 模型列表复制：双击单元格复制；右键复制模型 ID / 展示名 / 首字结果 / 整行 / 全部模型 ID；选中后 Ctrl+C | 模型表 |
| Key 显隐 / 复制 / 拖出 | API Key 行「显示」「复制」「拖动」 |
| 外观：浅色纸感 / 深色灰黑 / 跟随系统（实时切换） | 顶栏「设置」→ 外观 |
| 并发（1~8，默认 3）/ 超时（默认 10s） | 顶栏数字框 |
| 最大输出 Token（默认 8） | 顶栏「设置」 |

协议支持：**OpenAI Compatible**（自动补 `/v1`）、**Anthropic Messages**（不乱补路径，内部依次试 `/v1/...`）、**Gemini**（Key 走 query 参数）、**Zhipu / Z.AI v4**。Key 留空则不发送鉴权头（方便 Ollama / vLLM 等本地服务）。

## TTFT 口径

- 主指标 = 发出流式请求 → **第一条非空文本**，毫秒；TTFB 仅作参考不冒充。
- 空串 / 只有 role 的 chunk 不算首字；思考字段（`reasoning_content`、Anthropic `thinking`、Gemini `thought` part）算首字，结果标注来源。
- 流结束无文本 → 失败 `no_content`。
- 测速默认关思考（按厂商发禁用参数；服务端不认就自动去掉重试并标注）。强制思考模型标「首字来自思考字段 / 疑似强制思考」，不当故障。
- 测速请求默认 `max_tokens=8`，可在「设置」中调整；该值会写入测速结果，便于复现和比较。
- 拿到首字立即断流，省 token。
- 超时统一 10s（顶栏可调）。注意：重思考模型（如 glm-4.5）10s 内可能出不来首字，会记超时——这是按需求拍板的口径，想要慢模型数据就把超时调大。

## 结果记录与错误状态

- 每次单模型或批量测速都会保存该模型的最新结果，并在当前供应商下保留最近 500 条无 Key 历史记录（随 config.json 持久化，重启不丢）。
- 顶栏「历史」打开历史面板：条形图看各模型平均首字、折线图看单模型趋势，明细表可按供应商/模型筛选，面板内可直接导出 CSV 或清空。
- 连通结果会区分正常、可达但无模型列表、鉴权失败、限流、服务端错误、超时、网络错误、TLS 错误和 JSON/模型解析失败。

## 模型一致性检测

- 测速时从流式响应里读「上游实际使用的模型」：OpenAI 格式取 chunk 的 `model`，Anthropic 取 `message_start` 的 `message.model`，Gemini 取 `modelVersion`。
- 与请求的模型 ID 比对：**不一致**时首字结果会标 `· 上游:xxx` 并显示**琥珀色警示**；仅版本后缀差异（如 `glm-4.7:latest`、`models/` 前缀）只标注不警示；上游没报告则不标注。
- 悬停首字结果可看「请求 X · 上游返回 Y（判定）」明细；历史记录与导出的 CSV 都带 `reported_model` / `model_match` 字段。
- 典型用途：识别中转站/网关悄悄把请求路由到别的模型。

## 徽章

`T`=文本、`图`=图像输入、`听`、`视`，上下文（`1M` / `204800`），`想`=有思考档位（悬停看档位）。
数据来源优先级：接口字段 → 内置对照表（`app/catalog.py`，精确 id 再最长前缀）→ 名字启发式（vl/vision→图等）。**未知模型只标 T，不编造思考档。** 对照表直接改 `app/catalog.py` 即可。

## Key 安全

- 本地保存用 **Windows DPAPI** 加密（按当前用户绑定），配置文件里不存明文。
- 「复制」「拖动」是用户主动操作，输出明文 Key；掩码状态下复制的也是真 Key。
- 「拖动」按住按钮拖到记事本/浏览器/Cherry Studio 的输入框即可（标准 OLE 文本拖放，个别不接收文本拖放的目标请用「复制」）。
- 日志（`%APPDATA%\LLMApiTester\app.log`）不含任何 Key 与鉴权头。

## 注意

- exe 未签名，首次运行 SmartScreen 可能拦截：点「更多信息 → 仍要运行」。
- 全软件同一时刻只跑一个批量任务；批量测速时同供应商的单行测速会被拒。
- 测速会**真实调用模型**（prompt「回复一个字：好」，最大输出 Token 默认 8，可在设置调整），可能产生少量费用。
- 「跳过 TLS 校验」仅用于排查证书问题，有中间人风险。

## 目录

```
main.py               入口（含浅色调色板强制，深色系统模式下界面不花）
app/
  models.py           Provider / ModelRow
  config.py           %APPDATA% 持久化（Key DPAPI 加密）
  crypto_dpapi.py     DPAPI（ctypes，无第三方依赖）
  net.py              httpx 客户端 / 错误归类 / URL 校验（仅 http/https）
  protocols/          四种协议适配（headers、模型路径、SSE 首字解析、关思考参数）
  tester.py           连通性 + TTFT 引擎（SSE 解析、400 去参重试、首字断流）
  history.py          无 Key 测速历史记录与 CSV 导出
  taskman.py          后台 asyncio 线程 + Qt 信号（批量、并发、取消、互斥）
  catalog.py          模型徽章对照表 + 启发式
  ui.py               主界面
tests/
  smoke_offline.py    离线逻辑自检
  smoke_real.py       真实端点联调（Key 走环境变量）
  smoke_taskman.py    批量+取消管线冒烟
  seed_config.py      预置测试供应商到本机配置
  ui_grab.py          离屏截图自检
```

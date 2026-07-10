# 快速开始

## 安装

### 1. 安装

```bash
python install.py
```

### 2. 配置

```bash
python main.py setup
```

按提示选择：模型（推荐 DeepSeek）、人设、输入 API Key

### 3. 启动聊天

```bash
python main.py
```

---

## 新功能（v4.1）

### 🔌 内置 MCP 工具

启动后即可使用以下 MCP 工具（无需额外配置）：

| 工具 | 功能 |
|---|---|
| `get_weather` | 天气查询（wttr.in，免费） |
| `fetch` / `search` | 网页抓取 / Bing 搜索 |
| `get_datetime` / `random_number` | 日期时间 / 随机数 |
| `read_text_file` | 文件读取（安全白名单） |

输入 `/tools` 查看完整工具列表。

### 📷 图片识别

**直传模式（GPT-4o / Claude / Gemini 等多模态模型）**：无需配置，直接用 `/img photo.jpg`。

**降级模式（DeepSeek 等纯文本模型）**：在 `config/settings.json` 的 `advanced.vision_model` 中配置：

```json
{
  "advanced": {
    "vision_model": {
      "provider": "openai",
      "model_name": "gpt-4o",
      "api_key": "sk-your-key-here"
    }
  }
}
```

---

## 微信接入

### 前提条件
- 微信版本 v8.0.70+
- 已安装微信 ClawBot 插件

### 配置

```bash
python main.py wechat   # 扫码登录
python main.py           # 启动（自动连接微信）
```

---

## 常见问题

**Q: 安装失败？**
A: 检查 Python 版本（3.11+），重新运行 `install.py`

**Q: 微信扫码没反应？**
A: 确认已安装 ClawBot 插件，网络正常

**Q: MCP 工具不显示？**
A: 检查 `config/mcp_servers.json` 是否存在且正确配置，确保 Server 的命令可执行

**Q: 安全吗？**
A: MCP 文件读取有路径白名单限制，网页抓取有 SSRF 内网防护，仅允许安全目录和数据格式

**Q: 图片识别失败？**
A: 如果使用 DeepSeek 等文本模型，需要在 `settings.json` 配置视觉降级模型

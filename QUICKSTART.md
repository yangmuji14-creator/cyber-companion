# 快速开始

## 安装

### 1. 安装

运行命令：
```bash
python install.py
```

### 2. 配置

运行：
```bash
python main.py setup
```

按提示选择：
- 模型（推荐 DeepSeek）
- 人设（小雨）
- 输入 API Key

### 3. 启动聊天

```bash
python main.py
```

## 微信接入

### 前提条件
- 微信版本 v8.0.70+
- 已安装微信 ClawBot 插件（微信 → 我 → 设置 → 插件）

### 配置步骤

1. 运行 `python main.py wechat`
2. 按提示扫码登录
3. 登录成功后，以后运行 `python main.py` 会自动启动微信

### 使用

- 微信扫码后，给 AI 发消息就像聊天一样
- 本地命令行聊天同时可用
- 两边消息互通

## 常见问题

**Q: 安装失败？**
A: 检查 Python 版本（需要 3.11+），尝试重新运行 install.py

**Q: 微信扫码没反应？**
A: 确认已安装微信 ClawBot 插件，且网络正常

**Q: 微信消息收不到？**
A: 检查 `data/credentials/wechat.json` 是否存在，尝试重新运行 `python main.py wechat`

**Q: 如何关闭微信？**
A: 按 Ctrl+C 退出程序，微信会自动断开

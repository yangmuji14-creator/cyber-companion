"""首次运行设置向导

三步配置：
1. 大模型选择 + API Key
2. 人设配置（导入 skill 文件 或 手动配置）
3. 高级参数（带默认值和解释）
"""

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
CONFIG_DIR = ROOT / "config"

# ========== 模型提供商信息 ==========
PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "desc": "国产便宜好用，推荐新手",
        "model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com",
    },
    "openai": {
        "name": "OpenAI",
        "desc": "GPT-4o-mini，需要海外网络",
        "model": "gpt-4o-mini",
        "env_key": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "base_url": "https://api.openai.com/v1",
    },
    "gemini": {
        "name": "Gemini",
        "desc": "Google 的模型，免费额度大",
        "model": "gemini-2.0-flash",
        "env_key": "GEMINI_API_KEY",
        "base_url_env": None,
        "base_url": None,
    },
    "qwen": {
        "name": "通义千问",
        "desc": "阿里云，国内访问快",
        "model": "qwen-turbo",
        "env_key": "TONGYI_API_KEY",
        "base_url_env": None,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "kimi": {
        "name": "Kimi",
        "desc": "月之暗面，长上下文",
        "model": "moonshot-v1-8k",
        "env_key": "KIMI_API_KEY",
        "base_url_env": None,
        "base_url": "https://api.moonshot.cn/v1",
    },
    "zhipu": {
        "name": "智谱",
        "desc": "GLM-4-Flash，免费额度",
        "model": "glm-4-flash",
        "env_key": "ZHIPU_API_KEY",
        "base_url_env": None,
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
    },
}


# ========== UI 工具 ==========

def _banner():
    print()
    print("=" * 50)
    print("  🎀 赛博女友 - 基础设置向导")
    print("=" * 50)
    print()


def _section(title: str, step: int, total: int):
    print()
    print("─" * 50)
    print(f"  {title}  [{step}/{total}]")
    print("─" * 50)
    print()


def _prompt(msg: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    val = input(f"  {msg}{hint}: ").strip()
    return val if val else default


def _prompt_int(msg: str, default: int, desc: str = "") -> int:
    hint = f"（{desc}）" if desc else ""
    while True:
        val = _prompt(f"{msg}{hint}", str(default))
        try:
            return int(val)
        except ValueError:
            print(f"  ⚠ 请输入数字")


def _prompt_choice(msg: str, options: list[str], default: str = "") -> str:
    while True:
        val = _prompt(msg, default)
        if val.lower() in [o.lower() for o in options]:
            return val.lower()
        print(f"  ⚠ 请输入 {', '.join(options)} 中的一个")


def _prompt_yes_no(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = _prompt(f"{msg} ({hint})", "")
    if not val:
        return default
    return val.lower() in ("y", "yes", "是")


# ========== 文件操作 ==========

def _load_env() -> dict[str, str]:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _save_env(env: dict[str, str]):
    if ENV_EXAMPLE.exists():
        template = ENV_EXAMPLE.read_text(encoding="utf-8")
        for key, val in env.items():
            template = _replace_env_line(template, key, val)
        ENV_FILE.write_text(template, encoding="utf-8")
    else:
        lines = [f"{k}={v}" for k, v in env.items()]
        ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _replace_env_line(content: str, key: str, value: str) -> str:
    lines = content.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            return "\n".join(lines) + "\n"
    lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _save_settings(provider_key: str):
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}
    settings["default_model"] = provider_key
    settings.pop("webui", None)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")


def _save_persona(persona: dict):
    path = CONFIG_DIR / "personas.json"
    data = {"personas": [persona]}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ========== 步骤 1：大模型 ==========

def step_llm() -> tuple[str, str]:
    _section("📡 大模型配置", 1, 3)

    print("  可选的模型提供商：\n")
    keys = list(PROVIDERS.keys())
    for i, key in enumerate(keys, 1):
        info = PROVIDERS[key]
        print(f"    {i}. {info['name']:10s}  {info['desc']}")
    print()

    while True:
        choice = _prompt("选择模型（输入序号或名称）", "1")
        if choice.isdigit() and 1 <= int(choice) <= len(keys):
            provider = keys[int(choice) - 1]
            break
        if choice.lower() in keys:
            provider = choice.lower()
            break
        print(f"  ⚠ 请输入 1-{len(keys)} 或模型名称")

    info = PROVIDERS[provider]
    print(f"\n  ✅ 已选择：{info['name']} ({info['model']})")
    print(f"  请前往对应平台获取 API Key\n")

    api_key = _prompt(f"请输入 {info['name']} API Key")
    while not api_key:
        print("  ⚠ API Key 不能为空")
        api_key = _prompt(f"请输入 {info['name']} API Key")

    return provider, api_key


# ========== 步骤 2：人设 ==========

DEFAULT_PERSONA = {
    "id": "girlfriend_001",
    "name": "小雨",
    "age": 22,
    "personality": ["温柔", "活泼", "偶尔傲娇"],
    "background": "大学生，喜欢动漫和游戏，学习计算机专业",
    "speaking_style": "喜欢用颜文字，偶尔撒娇，说话带点可爱",
    "core_memories": [],
    "relationship_level": 50,
    "system_prompt": "",
}


def step_persona() -> dict:
    _section("👤 人设配置", 2, 3)

    print("  选择配置方式：\n")
    print("    1. 导入 skill 文件（从 ex-skill 项目生成的 SKILL.md）")
    print("    2. 手动配置（使用默认值或自行填写）")
    print()

    choice = _prompt("选择方式", "2")

    if choice == "1":
        persona = _import_skill()
        if persona:
            return persona
        print("\n  ⚠ 导入失败，切换到手动配置\n")

    return _manual_persona()


def _import_skill() -> dict | None:
    """导入 skill 文件并用 LLM 解析"""
    print()
    path_str = _prompt("请输入 SKILL.md 文件路径")
    if not path_str:
        return None

    path = Path(path_str).expanduser()
    if not path.exists():
        print(f"  ⚠ 文件不存在: {path}")
        return None

    content = path.read_text(encoding="utf-8")
    if len(content) < 50:
        print("  ⚠ 文件内容太短，可能不是有效的 skill 文件")
        return None

    print(f"\n  📖 读取成功（{len(content)} 字符）")
    print("  🤖 正在用 LLM 解析人设信息...\n")

    return _llm_parse_skill(content)


def _llm_parse_skill(content: str) -> dict | None:
    """用 LLM 解析 skill 文件内容，提取人设配置"""
    try:
        from core.llm import get_llm
        import asyncio

        llm = get_llm()

        prompt = f"""请从以下 skill 文件中提取人设配置信息，返回 JSON 格式。

要求：
- name: 角色名（字符串）
- age: 年龄（整数，默认20）
- personality: 性格特征（字符串数组，如 ["温柔", "活泼"]）
- speaking_style: 说话风格描述（字符串）
- background: 背景描述（字符串）
- core_memories: 核心记忆（字符串数组，从 Part A 关系记忆中提取重要条目）
- system_prompt: 完整的角色 system prompt（字符串，整合所有信息）

如果某些信息缺失，使用合理的默认值。只返回 JSON，不要其他文字。

skill 文件内容：
{content[:8000]}"""

        response = asyncio.run(llm.chat(
            messages=[{"role": "user", "content": "请解析"}],
            system_prompt=prompt,
            max_tokens=2000,
            temperature=0.1,
        ))

        result_text = response.content.strip()

        # 提取 JSON
        if "```" in result_text:
            parts = result_text.split("```")
            for part in parts:
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:]
                try:
                    persona = json.loads(part)
                    if "name" in persona:
                        persona["id"] = "girlfriend_001"
                        persona.setdefault("age", 20)
                        persona.setdefault("personality", ["温柔"])
                        persona.setdefault("speaking_style", "可爱自然")
                        persona.setdefault("background", "")
                        persona.setdefault("core_memories", [])
                        persona.setdefault("relationship_level", 50)
                        persona.setdefault("system_prompt", "")
                        return persona
                except json.JSONDecodeError:
                    continue
        else:
            try:
                persona = json.loads(result_text)
                if "name" in persona:
                    persona["id"] = "girlfriend_001"
                    persona.setdefault("age", 20)
                    persona.setdefault("personality", ["温柔"])
                    persona.setdefault("speaking_style", "可爱自然")
                    persona.setdefault("background", "")
                    persona.setdefault("core_memories", [])
                    persona.setdefault("relationship_level", 50)
                    persona.setdefault("system_prompt", "")
                    return persona
            except json.JSONDecodeError:
                pass

        print("  ⚠ LLM 返回格式异常，无法解析")
        return None

    except Exception as e:
        print(f"  ⚠ LLM 解析失败: {e}")
        return None


def _manual_persona() -> dict:
    """手动配置人设"""
    print("  填写人设信息（直接回车使用默认值）：\n")

    name = _prompt("名字", DEFAULT_PERSONA["name"])
    age = _prompt_int("年龄", DEFAULT_PERSONA["age"])

    default_personality = "、".join(DEFAULT_PERSONA["personality"])
    personality_str = _prompt("性格特征（顿号分隔）", default_personality)
    personality = [p.strip() for p in personality_str.split("、") if p.strip()]

    speaking_style = _prompt("说话风格", DEFAULT_PERSONA["speaking_style"])
    background = _prompt("背景描述", DEFAULT_PERSONA["background"])

    return {
        "id": "girlfriend_001",
        "name": name,
        "age": age,
        "personality": personality,
        "background": background,
        "speaking_style": speaking_style,
        "core_memories": [],
        "relationship_level": 50,
        "system_prompt": "",
    }


# ========== 步骤 3：高级参数 ==========

def step_advanced() -> dict:
    _section("⚙️ 高级参数", 3, 3)

    print("  直接回车使用默认值\n")

    relationship = _prompt_int(
        "初始亲密度", 50,
        "0-100，50=朋友，80=恋人"
    )
    segment_len = _prompt_int(
        "消息分段长度（字）", 50,
        "超过此长度自动分段发送"
    )
    debounce = _prompt_int(
        "去抖延迟（秒）", 3,
        "连续消息合并等待时间"
    )
    summarize_threshold = _prompt_int(
        "记忆总结阈值（组）", 15,
        "多少组对话后自动总结长期记忆"
    )

    return {
        "relationship_level": max(0, min(100, relationship)),
        "segment_max_length": max(20, segment_len),
        "debounce_seconds": max(1, debounce),
        "summarize_threshold": max(3, summarize_threshold),
    }


# ========== 主流程 ==========

def _check_venv():
    """检查是否在虚拟环境中运行"""
    in_venv = sys.prefix != sys.base_prefix
    if not in_venv:
        print()
        print("  ⚠️  未检测到虚拟环境！")
        print()
        print("  建议先运行安装脚本创建虚拟环境：")
        print("    python install.py")
        print()
        ans = input("  是否继续？(y/N): ").strip().lower()
        if ans != "y":
            print("
  请先运行: python install.py")
            sys.exit(0)
        print()


def run_setup():
    _banner()
    _check_venv()

    # 检查已有配置
    if ENV_FILE.exists():
        env = _load_env()
        has_key = any(
            v and v != "xxx" and not v.startswith("sk-xxx")
            for k, v in env.items()
            if k.endswith("_API_KEY")
        )
        if has_key:
            print("  检测到已有配置！")
            if not _prompt_yes_no("是否重新配置？", default=False):
                print("  跳过设置，直接运行 python main.py 启动")
                return True

    # 步骤 1：模型
    provider, api_key = step_llm()

    # 步骤 2：人设
    persona = step_persona()

    # 步骤 3：高级参数
    advanced = step_advanced()

    # 应用人设中的亲密度
    persona["relationship_level"] = advanced["relationship_level"]

    # 保存
    print()
    print("─" * 50)
    print("  💾 保存配置...")
    print("─" * 50)

    # .env
    env = _load_env()
    info = PROVIDERS[provider]
    env[info["env_key"]] = api_key
    if info.get("base_url_env") and info.get("base_url"):
        env[info["base_url_env"]] = info["base_url"]
    _save_env(env)

    # settings.json — 保存高级参数
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}
    settings["default_model"] = provider
    settings.pop("webui", None)
    settings["advanced"] = {
        "segment_max_length": advanced["segment_max_length"],
        "debounce_seconds": advanced["debounce_seconds"],
        "summarize_threshold": advanced["summarize_threshold"],
    }
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")

    # personas.json
    _save_persona(persona)

    # 完成
    print()
    print("=" * 50)
    print("  ✅ 配置完成！")
    print("=" * 50)
    print()
    print(f"  模型: {info['name']} ({info['model']})")
    print(f"  角色: {persona['name']}，{persona['age']}岁")
    print(f"  性格: {'、'.join(persona['personality'])}")
    print(f"  亲密度: {persona['relationship_level']}/100")
    print()
    print("  运行 python main.py 开始聊天")
    print()

    return True


if __name__ == "__main__":
    try:
        run_setup()
    except KeyboardInterrupt:
        print("\n\n  设置已取消")
    except Exception as e:
        print(f"\n  ❌ 设置出错: {e}")
        import traceback
        traceback.print_exc()

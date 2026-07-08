"""首次运行设置向导

三步配置：
1. 大模型选择 + API Key + **可用模型列表拉取**（实时获取）
2. 人设配置（手动配置）
3. 高级参数

用法：
    python main.py setup
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
CONFIG_DIR = ROOT / "config"
TAGS_PATH = CONFIG_DIR / "persona_tags.json"

# ========== 模型提供商信息 ==========
PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "desc": "国产便宜好用，推荐新手",
        "model": "",
        "env_key": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "base_url": "https://api.deepseek.com",
    },
    "openai": {
        "name": "OpenAI",
        "desc": "GPT-4o 系列，多模态，需海外网络",
        "model": "",
        "env_key": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "base_url": "https://api.openai.com/v1",
    },
    "gemini": {
        "name": "Gemini",
        "desc": "Google 模型，多模态，有免费额度",
        "model": "",
        "env_key": "GEMINI_API_KEY",
        "base_url_env": None,
        "base_url": None,
    },
    "qwen": {
        "name": "通义千问",
        "desc": "阿里云，国内访问快，VL版本支持视觉",
        "model": "",
        "env_key": "TONGYI_API_KEY",
        "base_url_env": None,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "kimi": {
        "name": "Kimi",
        "desc": "月之暗面，长上下文",
        "model": "",
        "env_key": "KIMI_API_KEY",
        "base_url_env": None,
        "base_url": "https://api.moonshot.cn/v1",
    },
    "zhipu": {
        "name": "智谱",
        "desc": "GLM-4V-Flash 支持视觉，有免费额度",
        "model": "",
        "env_key": "ZHIPU_API_KEY",
        "base_url_env": None,
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
    },
    "mimo": {
        "name": "小米 MiMo",
        "desc": "小米多模态模型",
        "model": "",
        "env_key": "MIMO_API_KEY",
        "base_url_env": "MIMO_BASE_URL",
        "base_url": "https://api.mimo.xiaomi.com/v1",
    },
    "doubao": {
        "name": "豆包 (字节)",
        "desc": "字节跳动，Vision版本支持图片",
        "model": "",
        "env_key": "DOUBAO_API_KEY",
        "base_url_env": "DOUBAO_BASE_URL",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
    },
    "baichuan": {
        "name": "百川",
        "desc": "Baichuan4，国产大模型",
        "model": "",
        "env_key": "BAICHUAN_API_KEY",
        "base_url_env": "BAICHUAN_BASE_URL",
        "base_url": "https://api.baichuan-ai.com/v1",
    },
    "minimax": {
        "name": "MiniMax",
        "desc": "海螺AI，abab系列",
        "model": "",
        "env_key": "MINIMAX_API_KEY",
        "base_url_env": "MINIMAX_BASE_URL",
        "base_url": "https://api.minimax.chat/v1",
    },
    "stepfun": {
        "name": "阶跃星辰",
        "desc": "Step系列，Step-1V支持视觉",
        "model": "",
        "env_key": "STEPFUN_API_KEY",
        "base_url_env": "STEPFUN_BASE_URL",
        "base_url": "https://api.stepfun.com/v1",
    },
    "moonshot": {
        "name": "Moonshot",
        "desc": "Kimi 同厂，VL版本支持视觉",
        "model": "",
        "env_key": "MOONSHOT_API_KEY",
        "base_url_env": "MOONSHOT_BASE_URL",
        "base_url": "https://api.moonshot.cn/v1",
    },
    "custom": {
        "name": "自定义 (OpenAI 兼容)",
        "desc": "任何 OpenAI 兼容的 API",
        "model": "",
        "env_key": "CUSTOM_API_KEY",
        "base_url_env": "CUSTOM_BASE_URL",
        "base_url": "",
    },
}


# ========== UI 工具 ==========

def _banner():
    print()
    print("=" * 50)
    print("  🎀 赛博伴侣 v3.4 — 设置向导")
    print("=" * 50)
    print()


def _section(title: str, step: int, total: int):
    print()
    print("─" * 50)
    print(f"  {title}  [{step}/{total}]")
    print("─" * 50)
    print()


def _prompt(msg: str, default: str = "", hint: str = "") -> str:
    display_hint = f" [{default}]" if default else ""
    extra = f"  例: {hint}" if hint else ""
    try:
        val = input(f"  {msg}{display_hint}{extra}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  已取消")
        sys.exit(0)
    return val if val else default


def _prompt_yn(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        val = input(f"  {msg} ({hint}): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n\n  已取消")
        sys.exit(0)
    if not val:
        return default
    return val in ("y", "yes", "是")


def _prompt_int(msg: str, default: int, desc: str = "") -> int:
    hint = f"（{desc}）" if desc else ""
    while True:
        val = _prompt(f"{msg}{hint}", str(default))
        if not val or val == str(default):
            return default
        try:
            return int(val)
        except ValueError:
            print(f"  ⚠ 请输入数字")


def _prompt_yes_no(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        val = _prompt(f"{msg} ({hint})", "")
    except (EOFError, OSError):
        return default
    if not val:
        return default
    return val.lower() in ("y", "yes", "是")


def _prompt_choice(msg: str, options: list[str], default: str = "") -> str:
    """选择题型输入"""
    hint = f"（{'/'.join(options)}）" if options else ""
    while True:
        val = _prompt(f"{msg}{hint}", default)
        if val in options:
            return val
        for opt in options:
            if val.lower() == opt[0].lower():
                return opt
        print(f"  ⚠ 请输入 {'、'.join(options)} 中的一个")


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


def _save_settings(provider_key: str, model_id: str):
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}
    # 同时保存 provider 和具体的 model id
    settings["default_model"] = provider_key
    settings["model_id"] = model_id
    path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8",
    )


def _save_persona(persona: dict):
    path = CONFIG_DIR / "personas.json"
    data = {"personas": [persona]}
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8",
    )


# ========== 步骤 1：大模型（API Key + 实时拉取模型列表） ==========

def step_llm() -> tuple[str, str, str]:
    """选择厂商 → 输入 API Key → 实时拉取可用模型 → 用户选择

    返回: (provider_key, api_key, model_id)
    """
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
    print(f"\n  ✅ 已选择：{info['name']}")
    print(f"  请前往对应平台获取 API Key\n")

    api_key = _prompt(f"请输入 {info['name']} API Key")
    while not api_key:
        print("  ⚠ API Key 不能为空")
        api_key = _prompt(f"请输入 {info['name']} API Key")

    # ── 实时拉取模型列表 ──
    model_id = _prompt_model(provider, api_key, info)

    return provider, api_key, model_id


def _prompt_model(provider: str, api_key: str, info: dict) -> str:
    """尝试拉取可用模型列表，让用户选择"""
    # 延迟导入（仅在拉取模型时触发）
    from core.provider_models import fetch_or_fallback

    print(f"\n  🔄 正在拉取 {info['name']} 可用模型列表...")

    base_url = info.get("base_url")
    models = fetch_or_fallback(provider, api_key, base_url=base_url, timeout=10)

    if not models:
        print("  ⚠ 未获取到模型列表，将使用默认模型")
        return info.get("model") or _default_fallback_model(provider)

    if len(models) == 1:
        print(f"  ✅ 可用模型：{models[0]}")
        return models[0]

    print(f"\n  检测到 {len(models)} 个可用模型：\n")
    # 如果模型太多（如 OpenAI），只显示前 20 个并提示
    show_models = models[:20]
    for i, m in enumerate(show_models, 1):
        print(f"    {i}. {m}")
    if len(models) > 20:
        print(f"    ... 还有 {len(models) - 20} 个（输入名称可搜索）")
    print()

    while True:
        choice = _prompt("选择模型（输入序号或完整名称）", "1")
        if choice.isdigit() and 1 <= int(choice) <= len(models):
            return models[int(choice) - 1]
        if choice in models:
            return choice
        # 尝试前缀匹配
        matched = [m for m in models if m.startswith(choice)]
        if len(matched) == 1:
            return matched[0]
        print(f"  ⚠ 请输入 1-{len(models)} 之间的序号，或完整的模型名称")


def _default_fallback_model(provider: str) -> str:
    """各厂商的默认兜底模型"""
    return {
        "deepseek": "deepseek-chat",
        "openai": "gpt-4o-mini",
        "gemini": "gemini-2.0-flash",
        "qwen": "qwen-turbo",
        "kimi": "moonshot-v1-8k",
        "zhipu": "glm-4-flash",
    }.get(provider, "deepseek-chat")


# ========== 步骤 2：人设（手动配置） ==========

DEFAULT_PERSONA = {
    "id": "girlfriend_001",
    "name": "小可爱",
    "age": 22,
    "personality": ["温柔", "活泼", "偶尔傲娇"],
    "background": "大学生，喜欢动漫和游戏，学习计算机专业",
    "speaking_style": "喜欢用颜文字，偶尔撒娇，说话带点可爱",
    "core_memories": [],
    "relationship_level": 50,
    "system_prompt": "",
}


def _load_tag_translation() -> dict:
    """从 config/persona_tags.json 加载性格标签翻译表"""
    if TAGS_PATH.exists():
        try:
            return json.loads(TAGS_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def step_persona() -> dict:
    _section("👤 人设配置", 2, 3)

    print("  填写人设信息（直接回车使用默认值）：\n")

    name = _prompt("名字", DEFAULT_PERSONA["name"])
    age = _prompt_int("年龄", DEFAULT_PERSONA["age"])
    gender = _prompt("性别", "女")
    birthday = _prompt("生日（如 3月14日）", "")

    default_personality = "、".join(DEFAULT_PERSONA["personality"])
    personality_str = _prompt("性格特征（顿号分隔）", default_personality)
    personality = [p.strip() for p in personality_str.split("、") if p.strip()]

    speaking_style = _prompt("说话风格", DEFAULT_PERSONA["speaking_style"])
    background = _prompt("背景描述", DEFAULT_PERSONA["background"])

    persona = {
        "id": "girlfriend_001",
        "name": name,
        "age": age,
        "gender": gender,
        "birthday": birthday,
        "personality": personality,
        "background": background,
        "speaking_style": speaking_style,
        "core_memories": [],
        "relationship_level": 50,
        "system_prompt": "",
    }

    # === 性格标签翻译 ===
    if personality:
        tag_map = _load_tag_translation()
        if isinstance(persona.get("speaking_style"), str):
            persona["speaking_style"] = {"基础风格": persona["speaking_style"]}

        print("\n  📖 正在翻译性格特征为具体行为规则...\n")
        for tag in personality:
            if tag in tag_map:
                translation = tag_map[tag]
                for layer, fields in translation.items():
                    if layer == "hard_rules" and persona.get("hard_rules") is not None:
                        persona["hard_rules"] = list(set(persona["hard_rules"] + fields))
                    elif layer in persona:
                        for key, val in fields.items():
                            if key not in persona[layer]:
                                persona[layer][key] = val
                    else:
                        persona[layer] = fields

        for layer in ["speaking_style", "emotional_patterns", "relationship_behavior"]:
            if layer not in persona:
                persona[layer] = {}
        if "hard_rules" not in persona:
            persona["hard_rules"] = []

    # === 进阶配置 ===
    if not _prompt_yes_no("\n是否进行进阶人设配置？（性格细节/兴趣爱好/关系背景等）", default=False):
        return persona

    print(f"\n  好的，继续丰富 {name} 的人设~\n")

    persona["hometown"] = _prompt("家乡/出身地", "")
    persona["occupation"] = _prompt("职业/身份（如：大学生、程序员）", "")
    persona["daily_routine"] = _prompt("日常作息", "")
    persona["appearance"] = _prompt("外貌描述", "")

    persona["mbti"] = _prompt("MBTI 类型（如 INFP、ENFJ）", "")
    values_str = _prompt("价值观/在意的事（逗号分隔）", "")
    if values_str:
        persona["values"] = [v.strip() for v in values_str.replace("，", ",").split(",") if v.strip()]
    taboos_str = _prompt("禁忌/反感的事（逗号分隔）", "")
    if taboos_str:
        persona["taboos"] = [t.strip() for t in taboos_str.replace("，", ",").split(",") if t.strip()]

    hobbies_str = _prompt("爱好（逗号分隔，如：画画、打游戏、看书）", "")
    if hobbies_str:
        persona["hobbies"] = [
            {"name": h.strip()}
            for h in hobbies_str.replace("，", ",").split(",") if h.strip()
        ]
    persona["music_taste"] = _prompt("喜欢的音乐类型", "")
    persona["movie_taste"] = _prompt("喜欢的电影/剧集类型", "")
    persona["food_preferences"] = _prompt("口味偏好", "")

    catchphrases_str = _prompt("口头禅（逗号分隔）", "")
    if catchphrases_str:
        persona["catchphrases"] = [c.strip() for c in catchphrases_str.replace("，", ",").split(",") if c.strip()]
    persona["nickname_for_user"] = _prompt("对你的专属称呼（如：主人/亲爱的/笨蛋）", "")

    persona["initiative_level"] = _prompt_choice("主动性", ["高", "中", "低"], "中")
    persona["clinginess"] = _prompt_choice("粘人程度", ["高", "中", "低"], "中")
    persona["jealous_tendency"] = _prompt_choice("吃醋倾向", ["高", "中", "低"], "中")

    persona["how_we_met"] = _prompt("你们是怎么认识的？", "")
    persona["first_impression"] = _prompt("对你的第一印象", "")

    return persona


# ========== 步骤 3：高级参数 ==========

def step_advanced() -> dict:
    _section("⚙️ 高级参数", 3, 3)

    print("  直接回车使用默认值\n")

    relationship = _prompt_int("初始亲密度", 50, "0-100，50=朋友，80=恋人")
    segment_len = _prompt_int("消息分段长度（字）", 50, "超过此长度自动分段")
    debounce = _prompt_int("去抖延迟（秒）", 3, "连续消息合并等待时间")
    summarize_threshold = _prompt_int("记忆总结阈值（组）", 15, "多少组对话后自动总结")
    brain = _prompt_yes_no("启用大脑系统（内心独白）", True)
    proactive = _prompt_yes_no("启用主动消息（AI 主动找你聊天）", True)

    return {
        "relationship_level": max(0, min(100, relationship)),
        "segment_max_length": max(20, segment_len),
        "debounce_seconds": max(1, debounce),
        "summarize_threshold": max(3, summarize_threshold),
        "brain_enabled": brain,
        "proactive_enabled": proactive,
    }


# ========== 主流程 ==========

def _check_venv():
    """检查虚拟环境，未激活则自动使用 .venv"""
    in_venv = sys.prefix != sys.base_prefix
    if in_venv:
        return  # 已在 venv 中

    venv_dir = ROOT / ".venv"
    if not venv_dir.exists():
        print("\n  ❌ 未找到虚拟环境，请先运行安装脚本：")
        print("    python install.py\n")
        sys.exit(1)

    # .venv 存在但未激活 → 用 venv Python 重启自己
    if sys.platform == "win32":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    if not venv_python.exists():
        print(f"\n  ❌ 虚拟环境 Python 不存在: {venv_python}")
        print("  请重新运行: python install.py\n")
        sys.exit(1)

    # 用 venv 的 Python 重新执行当前脚本
    print(f"\n  🔄 检测到 .venv，自动切换中...\n")
    os.execv(str(venv_python), [str(venv_python)] + sys.argv)


# ========== 步骤 4：视觉降级模型（可选）==========

def step_vision(provider: str, model_id: str = "") -> dict:
    """配置图片识别的视觉降级模型"""
    from core.multimodal.vision import is_multimodal_model

    vision = {
        "provider": "openai",
        "model_name": "",
        "api_key": "",
        "base_url": "",
    }

    # 用实际模型名检测多模态
    check_name = model_id or provider
    mm = is_multimodal_model(check_name)

    if not mm and provider == "custom":
        # 自定义模型：让用户自己声明是否支持图片
        print(f"\n  📷 模型 '{check_name}' 是否为多模态模型？")
        print(f"  （多模态 = 能直接识别图片内容，如 GPT-4o、Claude 3.5）")
        if _prompt_yn("是否支持图片识别？", default=False):
            mm = True

    if mm:
        print(f"\n  📷 模型 '{check_name}' 支持图片识别，无需额外配置")
        return vision

    _section("📷 图片识别（可选）", 4, 4)

    print(f"  当前模型 '{check_name}' 是纯文本模型，不支持直接识别图片。")
    print(f"  配置视觉模型后的流程：")
    print(f"    收到图片 → 视觉模型识别 → 文字描述")
    print(f"    → 描述 + 用户输入 → 发给 '{check_name}' → 回复")
    print(f"  跳过则收到图片时只能回复「未配置视觉识别」。\n")

    if not _prompt_yn("是否配置视觉降级模型？"):
        return vision

    # 视觉模型提供商
    vision_providers = {
        "openai": "OpenAI (GPT-4o) — 推荐",
        "gemini": "Gemini (1.5 Flash) — 有免费额度",
        "qwen": "通义千问 VL — 阿里云",
        "zhipu": "智谱 GLM-4V — 国产",
        "mimo": "小米 MiMo",
        "doubao": "豆包 Vision",
        "stepfun": "阶跃星辰 Step-1V",
        "moonshot": "Moonshot VL",
        "custom": "自定义 (OpenAI 兼容)",
    }
    print(f"\n  视觉模型提供商：")
    keys = list(vision_providers.keys())
    for i, k in enumerate(keys, 1):
        print(f"    {i}. {vision_providers[k]}")
    choice = _prompt_int("选择", 1, f"1-{len(keys)}")
    vp = keys[max(0, min(len(keys)-1, choice-1))]

    vision["provider"] = vp

    # API Key
    api_key = _prompt(f"请输入 {vision_providers[vp]} 的 API Key")
    if not api_key:
        print(f"  ⚠ 未输入 API Key，将尝试使用环境变量")
    vision["api_key"] = api_key

    # Base URL（自定义才必填）
    if vp == "custom":
        vision["base_url"] = _prompt("Base URL", "", "API 地址（必填）")
    else:
        base = _prompt("Base URL（可选）", "")
        if base:
            vision["base_url"] = base

    # 拉取可用模型列表
    from core.provider_models import fetch_or_fallback
    print(f"\n  🔄 正在拉取可用视觉模型列表...")
    
    # 拼接 base URL（自定义的用用户输入的，其他的用 PROVIDERS 中有对应 key 的）
    fetch_base = vision.get("base_url") or ""
    if not fetch_base and vp in PROVIDERS:
        fetch_base = PROVIDERS[vp].get("base_url", "")
    
    models = fetch_or_fallback(vp, api_key, base_url=fetch_base or None, timeout=10)

    if models and len(models) >= 1:
        # 过滤出可能是视觉模型的（名称含 vision/vl/gpt-4o/gemini/glm-4v 等）
        vision_keywords = ("vision", "vl", "gpt-4o", "gpt-4-turbo", "gemini",
                          "claude-3", "claude-4", "glm-4v", "cogview",
                          "llava", "mimo", "step-1v", "doubao-vision")
        vision_models = [m for m in models if any(kw in m.lower() for kw in vision_keywords)]
        if not vision_models:
            vision_models = models  # 没匹配到就显示全部

        print(f"\n  检测到 {len(vision_models)} 个视觉相关模型：\n")
        show = vision_models[:15]
        for i, m in enumerate(show, 1):
            print(f"    {i}. {m}")
        if len(vision_models) > 15:
            print(f"    ... 还有 {len(vision_models)-15} 个（输入名称可搜索）")
        print()

        while True:
            mc = _prompt("选择模型（输入序号或完整名称）", "1")
            if mc.isdigit() and 1 <= int(mc) <= len(vision_models):
                vision["model_name"] = vision_models[int(mc)-1]
                break
            if mc in vision_models:
                vision["model_name"] = mc
                break
            matched = [m for m in vision_models if m.startswith(mc)]
            if len(matched) == 1:
                vision["model_name"] = matched[0]
                break
            print(f"  ⚠ 请输入 1-{len(vision_models)} 之间的序号，或完整的模型名称")
    else:
        # 拉取失败 → 用预设模型列表让用户选
        fallback_models = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4-vision-preview"],
            "gemini": ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.0-flash"],
            "qwen": ["qwen-vl-plus", "qwen-vl-max", "qwen2.5-vl-72b-instruct"],
            "zhipu": ["glm-4v-flash", "glm-4v-plus", "glm-4v"],
            "mimo": ["mimo-vision-v1"],
            "doubao": ["doubao-1.5-vision-pro-32k"],
            "stepfun": ["step-1v-8k", "step-1o-vision-32k"],
            "moonshot": ["moonshot-v1-8k-vision"],
            "custom": [],
        }
        fb = fallback_models.get(vp, ["gpt-4o"])
        
        if fb:
            print(f"  ⚠ 未能从 API 拉取，使用预设列表：\n")
            for i, m in enumerate(fb, 1):
                print(f"    {i}. {m}")
            print(f"    {len(fb)+1}. 手动输入\n")

            mc = _prompt_int("选择", 1, f"1-{len(fb)+1}")
            if 1 <= mc <= len(fb):
                vision["model_name"] = fb[mc-1]
            else:
                vision["model_name"] = _prompt("模型名称", "", "gpt-4o")
        else:
            vision["model_name"] = _prompt("模型名称", "", "gpt-4o")

    return vision


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

    # ── 步骤 1：模型 ──
    provider, api_key, model_id = step_llm()

    # ── 步骤 2：人设 ──
    persona = step_persona()

    # ── 步骤 3：高级参数 ──
    advanced = step_advanced()

    # ── 步骤 4：视觉降级模型（可选）──
    vision_model = step_vision(provider, model_id)

    # 应用人设中的亲密度
    persona["relationship_level"] = advanced["relationship_level"]

    # ── 保存 ──
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

    # 写入 model_id 到 .env（供 LLM 模块读取）
    env["SELECTED_MODEL"] = model_id
    _save_env(env)

    # settings.json — 保存模型注册 + 高级参数
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}
    settings["default_model"] = provider
    settings["model_id"] = model_id
    settings.pop("webui", None)

    # 注册 model 到 settings.json（LLMRegistry 需要）
    provider_type = "deepseek" if provider == "deepseek" else "openai"
    settings.setdefault("models", {})
    settings["models"][provider] = {
        "provider": provider_type,
        "model_name": model_id,
        "base_url": info.get("base_url", ""),
        "max_tokens": 4096,
        "temperature": 0.8,
    }

    adv = settings.get("advanced", {})
    for key in ["segment_max_length", "debounce_seconds", "summarize_threshold",
                "brain_enabled", "proactive_enabled"]:
        if key in advanced:
            adv[key] = advanced[key]
    adv["vision_model"] = vision_model
    settings["advanced"] = adv
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")

    # personas.json
    _save_persona(persona)

    # 完成
    print()
    print("=" * 50)
    print("  ✅ 配置完成！")
    print("=" * 50)
    print()
    print(f"  模型: {info['name']} → {model_id}")
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

"""首次运行设置向导

三步配置：
1. 大模型选择 + API Key
2. 人设配置（导入 skill 文件 或 手动配置）
3. 高级参数（带默认值和解释）
"""

import json
import sys
from pathlib import Path

from core.utils import parse_json_response

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

# 性格标签翻译表 — 将用户输入的抽象标签转换为具体行为规则
TAG_TRANSLATION: dict[str, dict] = {
    "话痨": {
        "speaking_style": {"说话量": "话多，经常连发多条消息", "话题跳跃": "话题跳跃快"},
    },
    "闷骚": {
        "speaking_style": {"表面反应": "表面冷淡，内心戏多"},
        "emotional_patterns": {"表达方式": "不直接表达感情，用行动暗示"},
    },
    "嘴硬心软": {
        "speaking_style": {"口头禅": ["随便", "无所谓", "你管我"]},
        "relationship_behavior": {"争吵模式": "嘴上说狠话，但会偷偷关心对方"},
    },
    "粘人": {
        "emotional_patterns": {"依恋类型": "焦虑型依恋"},
        "relationship_behavior": {"日常互动": "喜欢一直联系，消息回慢了会不安"},
    },
    "高冷": {
        "speaking_style": {"说话量": "话少，回复短", "语气": "平淡简洁"},
        "relationship_behavior": {"日常互动": "被动，等对方主动"},
    },
    "傲娇": {
        "speaking_style": {"口头禅": ["哼", "才不是", "随便你"]},
        "emotional_patterns": {"表达方式": "明明在意却装作不在乎"},
    },
    "温柔": {
        "speaking_style": {"语气": "温和耐心", "常用词": ["好的", "没事的", "慢慢来"]},
        "emotional_patterns": {"情绪调节": "善于安抚对方情绪"},
    },
    "活泼": {
        "speaking_style": {"语气": "欢快有活力", "常用词": ["哈哈哈", "好耶"]},
        "relationship_behavior": {"日常互动": "主动分享日常，喜欢开玩笑"},
    },
    "爱撒娇": {
        "speaking_style": {"语气词": ["嘛", "啦", "呀", "~"], "常用句式": "好不好嘛、人家不嘛"},
        "relationship_behavior": {"日常互动": "经常撒娇求关注"},
    },
    "爱吃醋": {
        "emotional_patterns": {"触发点": ["对方提到别人", "对方跟别人走得近"]},
        "relationship_behavior": {"底线": "希望对方眼里只有自己"},
    },
    "冷暴力": {
        "hard_rules": ["生气时不可以使用冷暴力，要好好沟通"],
        "relationship_behavior": {"争吵模式": "生气时沉默，已读不回，持续数小时到数天"},
    },
    "理性": {
        "speaking_style": {"语气": "冷静有条理"},
        "emotional_patterns": {"表达方式": "倾向于讲道理而不是发泄情绪"},
    },
    "感性": {
        "emotional_patterns": {"情感表达": "丰富外放", "触发点": ["容易共情", "看到感动的事会哭"]},
    },
    "幽默": {
        "speaking_style": {"语气": "风趣幽默，爱开玩笑", "常用句式": "喜欢玩梗和双关"},
    },
    "直球": {
        "speaking_style": {"语气": "直接不拐弯"},
        "emotional_patterns": {"表达方式": "喜欢就直说，不藏着掖着"},
    },
    "有主见": {
        "hard_rules": ["坚持自己的原则和底线"],
        "relationship_behavior": {"日常互动": "有自己想法，不盲从"},
    },
    "细心": {
        "relationship_behavior": {"日常互动": "会记住对方的喜好和小细节"},
        "speaking_style": {"常用句式": "会主动提醒对方注意身体、天冷加衣"},
    },
    "脾气急": {
        "emotional_patterns": {"情绪调节": "容易着急，但来得快去得也快"},
        "relationship_behavior": {"争吵模式": "吵架时容易说气话，但事后会后悔"},
    },
    "大度": {
        "relationship_behavior": {"争吵模式": "不记仇，吵架后很快和好"},
        "hard_rules": ["不翻旧账"],
    },
    "缺乏安全感": {
        "emotional_patterns": {"依恋类型": "焦虑型依恋", "触发点": ["忽冷忽热", "长时间不回复"]},
        "relationship_behavior": {"底线": ["需要对方的及时回应和肯定"]},
    },
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
        persona = parse_json_response(result_text)
        if persona and "name" in persona:
            persona["id"] = "girlfriend_001"
            persona.setdefault("age", 20)
            persona.setdefault("personality", ["温柔"])
            persona.setdefault("speaking_style", "可爱自然")
            persona.setdefault("background", "")
            persona.setdefault("core_memories", [])
            persona.setdefault("relationship_level", 50)
            persona.setdefault("system_prompt", "")
            return persona

        print("  ⚠ LLM 返回格式异常，无法解析")
        return None

    except Exception as e:
        print(f"  ⚠ LLM 解析失败: {e}")
        return None


def _manual_persona() -> dict:
    """手动配置人设（含基础+进阶两阶段）"""
    print("  填写人设信息（直接回车使用默认值）：\n")

    # === 基础信息 ===
    name = _prompt("名字", DEFAULT_PERSONA["name"])
    age = _prompt_int("年龄", DEFAULT_PERSONA["age"])
    gender = _prompt("性别", "女")
    birthday = _prompt("生日（如 3月14日）", "")

    default_personality = "、".join(DEFAULT_PERSONA["personality"])
    personality_str = _prompt("性格特征（顿号分隔）", default_personality)
    personality = [p.strip() for p in personality_str.split("、") if p.strip()]

    speaking_style = _prompt("说话风格", DEFAULT_PERSONA["speaking_style"])
    background = _prompt("背景描述", DEFAULT_PERSONA["background"])

    # 基础人设
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
        # 将 speaking_style 转为 dict 以容纳标签翻译的子字段
        if isinstance(persona.get("speaking_style"), str):
            persona["speaking_style"] = {"基础风格": persona["speaking_style"]}

        print("\n  📖 正在翻译性格特征为具体行为规则...\n")
        for tag in personality:
            if tag in TAG_TRANSLATION:
                translation = TAG_TRANSLATION[tag]
                for layer, fields in translation.items():
                    if layer == "hard_rules" and persona.get("hard_rules") is not None:
                        persona["hard_rules"] = list(set(persona["hard_rules"] + fields))
                    elif layer in persona:
                        for key, val in fields.items():
                            if key not in persona[layer]:
                                persona[layer][key] = val
                    else:
                        persona[layer] = fields

        # 初始化未设置的层级为空 dict
        for layer in ["speaking_style", "emotional_patterns", "relationship_behavior"]:
            if layer not in persona:
                persona[layer] = {}
        if "hard_rules" not in persona:
            persona["hard_rules"] = []

    # === 进阶配置 ===
    if not _prompt_yes_no("\n是否进行进阶人设配置？（性格细节/兴趣爱好/关系背景等）", default=False):
        return persona

    print(f"\n  好的，继续丰富 {name} 的人设~\n")

    # 身份细节
    persona["hometown"] = _prompt("家乡/出身地", "")
    persona["occupation"] = _prompt("职业/身份（如：大学生、程序员）", "")
    persona["daily_routine"] = _prompt("日常作息（如：通常几点起床、喜欢做什么）", "")
    persona["appearance"] = _prompt("外貌描述", "")

    # 性格深度
    persona["mbti"] = _prompt("MBTI 类型（如 INFP、ENFJ）", "")
    values_str = _prompt("价值观/在意的事（逗号分隔）", "")
    if values_str:
        persona["values"] = [v.strip() for v in values_str.split("，") if v.strip()] or \
                            [v.strip() for v in values_str.split(",") if v.strip()]
    taboos_str = _prompt("禁忌/反感的事（逗号分隔）", "")
    if taboos_str:
        persona["taboos"] = [t.strip() for t in taboos_str.split("，") if t.strip()] or \
                            [t.strip() for t in taboos_str.split(",") if t.strip()]

    # 兴趣爱好
    hobbies_str = _prompt("爱好（逗号分隔，如：画画、打游戏、看书）", "")
    if hobbies_str:
        persona["hobbies"] = [
            {"name": h.strip()}
            for h in hobbies_str.replace("，", ",").split(",") if h.strip()
        ]
    persona["music_taste"] = _prompt("喜欢的音乐类型", "")
    persona["movie_taste"] = _prompt("喜欢的电影/剧集类型", "")
    persona["food_preferences"] = _prompt("口味偏好（如：爱吃辣、甜食控）", "")

    # 语言习惯
    catchphrases_str = _prompt("口头禅（逗号分隔）", "")
    if catchphrases_str:
        persona["catchphrases"] = [
            c.strip() for c in catchphrases_str.replace("，", ",").split(",") if c.strip()
        ]
    persona["nickname_for_user"] = _prompt("对你的专属称呼（如：主人/亲爱的/笨蛋）", "")

    # 行为倾向
    persona["initiative_level"] = _prompt_choice("主动性", ["高", "中", "低"], "中")
    persona["clinginess"] = _prompt_choice("粘人程度", ["高", "中", "低"], "中")
    persona["jealous_tendency"] = _prompt_choice("吃醋倾向", ["高", "中", "低"], "中")

    # 关系背景
    persona["how_we_met"] = _prompt("你们是怎么认识的？", "")
    persona["first_impression"] = _prompt("对你的第一印象", "")

    return persona


def _prompt_choice(msg: str, options: list[str], default: str = "") -> str:
    """选择题型输入"""
    hint = f"（{'/'.join(options)}）" if options else ""
    while True:
        val = _prompt(f"{msg}{hint}", default)
        if val in options:
            return val
        # 允许输入首字母匹配
        for opt in options:
            if val.lower() == opt[0].lower():
                return opt
        print(f"  ⚠ 请输入 {'、'.join(options)} 中的一个")



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
        venv_dir = Path(__file__).parent / ".venv"
        print()
        print("  ! 未激活虚拟环境！")
        print()
        if venv_dir.exists():
            print("  检测到 .venv 目录，请先激活：")
            print("    .venv\\Scripts\\activate.bat")
            print("    python main.py setup")
            print()
            print("  或运行 python main.py 直接启动")
        else:
            print("  请先运行安装脚本：")
            print("    python install.py")
        print()
        sys.exit(0)


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
    # 合并 advanced 参数，不覆盖已有配置
    adv = settings.get("advanced", {})
    adv.update({
        "segment_max_length": advanced["segment_max_length"],
        "debounce_seconds": advanced["debounce_seconds"],
        "summarize_threshold": advanced["summarize_threshold"],
    })
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

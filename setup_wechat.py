"""微信 Bot 配置向导

独立于主设置向导（setup_wizard.py），也可被 setup_wizard 末尾引导调用。

用法：
    独立运行：  python setup_wechat.py
    程序调用：  from setup_wechat import run_wechat_setup; run_wechat_setup()
    CLI 命令：  python main.py wechat
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
CREDENTIALS_FILE = ROOT / "data" / "credentials" / "wechat.json"


# ========== UI 工具 ==========

def _banner():
    print()
    print("=" * 50)
    print("  💬 微信 Bot 配置向导")
    print("=" * 50)
    print()


def _prompt(msg: str, default: str = "") -> str:
    display_hint = f" [{default}]" if default else ""
    try:
        val = input(f"  {msg}{display_hint}: ").strip()
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


# ========== 配置存储 ==========

def _has_credentials() -> bool:
    return CREDENTIALS_FILE.exists()


def _save_adapter_config(enabled: bool = True, auto_start: bool = True) -> None:
    """将微信适配器配置写入 config/settings.json"""
    path = CONFIG_DIR / "settings.json"
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}

    settings.setdefault("advanced", {})
    settings["advanced"].setdefault("adapters", {})
    settings["advanced"]["adapters"]["wechat"] = {
        "enabled": enabled,
        "auto_start": auto_start,
    }

    path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8",
    )


# ========== 主流程 ==========

def run_wechat_setup() -> bool:
    """运行微信配置向导，返回是否配置成功

    可以被 setup_wizard.py 或 main.py 调用。
    """
    _banner()

    # ── 检查已有配置 ──
    if _has_credentials():
        print("  检测到已有微信登录凭证！")
        print(f"  凭证位置: {CREDENTIALS_FILE}")
        print()
        if not _prompt_yn("是否重新登录？", default=False):
            print("\n  跳过微信配置，现有凭证继续有效。")
            _save_adapter_config(enabled=True, auto_start=True)
            return True

    # ── 前置条件 ──
    print()
    print("  准备工作：")
    print("  1. 手机上安装微信 ClawBot 插件")
    print("  2. 确保手机微信已登录目标账号")
    print("  3. 保持手机与电脑在同一个网络")
    print()

    if not _prompt_yn("准备好了，开始扫码?", default=True):
        print("\n  已跳过微信配置。以后可以运行 python main.py wechat 重新配置。")
        return False

    # ── SDK 检查 ──
    try:
        from weixin_ilink import login  # noqa: F401
    except ImportError:
        print()
        print("  ❌ weixin-ilink 未安装")
        print()
        print("  请先运行：")
        print("    python install.py")
        print()
        input("  按回车键退出...")
        return False

    # ── 扫码登录 ──
    print()
    print("─" * 50)
    print("  正在获取二维码...")
    print("─" * 50)

    try:
        from adapters.wechat import WeChatAdapter
        adapter = WeChatAdapter()
        asyncio.run(adapter.start())
    except Exception as e:
        print(f"\n  ❌ 微信登录失败: {e}")
        print()
        print("  常见问题：")
        print("  - 手机端是否安装了 ClawBot 插件？")
        print("  - 二维码是否过期？（重新运行尝试）")
        print("  - 网络是否正常？")
        print()
        input("  按回车键退出...")
        return False

    # ── 验证凭证是否保存 ──
    if not _has_credentials():
        print("\n  ⚠ 未检测到登录凭证，登录可能失败。")
        print("  请重新运行 python main.py wechat 尝试。")
        input("  按回车键退出...")
        return False

    # ── 配置选项 ──
    print()
    print("─" * 50)
    print("  微信 Bot 配置选项")
    print("─" * 50)
    print()
    auto_start = _prompt_yn("启动主程序时自动启动微信 Bot？", default=True)

    _save_adapter_config(enabled=True, auto_start=auto_start)

    # ── 完成 ──
    print()
    print("=" * 50)
    print("  ✅ 微信 Bot 配置完成！")
    print("=" * 50)
    print()
    if auto_start:
        print("  以后运行 python main.py 会自动启动微信 Bot")
    else:
        print("  运行 python main.py 时不会自动启动微信")
        print("  需要微信时请运行: python main.py wechat")
    print(f"  登录凭证已保存至: {CREDENTIALS_FILE}")
    print()

    return True


if __name__ == "__main__":
    try:
        run_wechat_setup()
    except KeyboardInterrupt:
        print("\n\n  设置已取消\n")
    except Exception as e:
        print(f"\n  ❌ 未知错误: {e}")
        import traceback
        traceback.print_exc()
        input("\n  按回车键退出...")

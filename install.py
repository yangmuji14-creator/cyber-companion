"""环境安装脚本

自动检测可用的安装工具（uv > pip），创建虚拟环境并安装依赖。
支持国内镜像源自动切换。

用法：
    python install.py               # 默认安装（核心依赖）
    python install.py --dev         # 安装核心 + 开发依赖（pytest 等）
    python install.py --all         # 安装核心 + 开发 + 可选依赖（向量记忆等）
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).parent
VENV_DIR = ROOT / ".venv"
REQ_FILE = ROOT / "requirements.txt"
REQ_DEV_FILE = ROOT / "requirements-dev.txt"

# 国内镜像源（按优先级排列）
MIRRORS = [
    ("清华", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里", "https://mirrors.aliyun.com/pypi/simple"),
    ("中科大", "https://mirrors.ustc.edu.cn/pypi/web/simple"),
    ("官方", "https://pypi.org/simple"),
]

PYTHON_MIN = (3, 11)


# ========== 工具检测 ==========

def _has_uv() -> bool:
    """检测系统是否安装了 uv"""
    return shutil.which("uv") is not None


def _check_python():
    v = sys.version_info[:2]
    if v < PYTHON_MIN:
        print(f"  ❌ 需要 Python {PYTHON_MIN[0]}.{PYTHON_MIN[1]}+，当前 {v[0]}.{v[1]}")
        print(f"     请前往 https://www.python.org/downloads/ 下载")
        sys.exit(1)
    print(f"  ✅ Python {v[0]}.{v[1]}")
    if _has_uv():
        print(f"  ✅ 检测到 uv，安装速度更快！")


# ========== 虚拟环境 ==========

def _create_venv():
    if VENV_DIR.exists():
        print(f"  📁 虚拟环境已存在: {VENV_DIR}")
        ans = input("  是否重建？(y/N): ").strip().lower()
        if ans != "y":
            print("  跳过创建，使用现有环境")
            return
        shutil.rmtree(VENV_DIR)
        print("  🗑️  已删除旧环境")

    print("  🔧 创建虚拟环境...")
    subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        check=True,
    )
    print(f"  ✅ 虚拟环境创建成功: {VENV_DIR}")


def _get_pip_cmd() -> list[str]:
    """获取 venv 中的 pip 命令"""
    if sys.platform == "win32":
        pip = VENV_DIR / "Scripts" / "pip.exe"
    else:
        pip = VENV_DIR / "bin" / "pip"
    return [str(pip)]


def _get_uv_cmd() -> list[str]:
    """获取 venv 中的 uv pip 命令"""
    return ["uv", "pip"]


# ========== 依赖安装 ==========

def _run_pip(args: list[str]) -> tuple[int, str]:
    """安装命令，实时显示进度"""
    env = {**os.environ, "PYTHONUTF8": "1"}
    all_output: list[str] = []
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    for raw_line in iter(proc.stdout.readline, b""):
        line = raw_line.decode("utf-8", errors="replace")
        all_output.append(line)
        print(f"  {line}", end="", flush=True)
    proc.wait()
    return proc.returncode, "".join(all_output)


def _install_using(pip_base: list[str], req_paths: list[Path]) -> bool:
    """使用给定的 pip 命令（原生 pip 或 uv pip）安装依赖

    对原生 pip 尝试所有镜像源；对 uv 只用官方源（uv 走 CDN 已经很快）。
    """
    using_uv = pip_base[0] == "uv"

    if using_uv:
        # uv 自带 CDN 加速，直接装
        for req in req_paths:
            print(f"\n  → 安装 {req.name}...")
            cmd = pip_base + ["install", "-r", str(req)]
            ret, _ = _run_pip(cmd)
            if ret != 0:
                print(f"  ❌ 安装 {req.name} 失败")
                return False
        return True

    # 原生 pip：尝试各个镜像源
    for req in req_paths:
        print(f"\n  → 安装 {req.name}...")
        success = False
        for name, url in MIRRORS:
            print(f"    源: {name} ({url})")
            cmd = pip_base + ["install", "-r", str(req), "-i", url, "--timeout", "120"]
            ret, out_text = _run_pip(cmd)
            if ret == 0:
                success = True
                break
            _print_error_hint(out_text)
            print()

        if not success:
            print(f"  ❌ 安装 {req.name} 失败，请检查网络连接")
            print()
            print("  你也可以尝试手动安装：")
            print(f"    {' '.join(pip_base)} install -r {req}")
            return False

    return True


def _print_error_hint(text: str):
    """提取关键错误信息"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    show = []
    for line in lines[-10:]:
        if any(kw in line.lower() for kw in
               ["error", "could not", "connection", "timeout",
                "no matching", "not found", "ssl"]):
            show.append(line)
    if show:
        for line in show[-3:]:
            print(f"    ⚠ {line}")


# ========== 可选依赖 ==========

def _install_optional(pip_base: list[str], name: str, pkg: str):
    """安装单个可选依赖"""
    ans = input(f"  是否安装 {name}？(y/N): ").strip().lower()
    if ans != "y":
        return
    print(f"  → 安装 {pkg}...")
    cmd = pip_base + ["install", pkg]
    ret, _ = _run_pip(cmd)
    if ret == 0:
        print(f"  ✅ {name} 安装成功")
    else:
        print(f"  ⚠ {name} 安装失败，可稍后手动安装：{' '.join(cmd)}")


# ========== 主流程 ==========

def main():
    import argparse

    parser = argparse.ArgumentParser(description="赛博伴侣 — 环境安装")
    parser.add_argument("--dev", action="store_true", help="安装开发依赖（pytest 等）")
    parser.add_argument("--all", action="store_true", help="安装全部（含可选依赖）")
    args = parser.parse_args()

    print()
    print("=" * 50)
    print("  🎀 赛博伴侣 - 环境安装")
    print("=" * 50)
    print()

    # [1/4] 检查 Python
    print("  [1/4] 检查 Python 版本")
    _check_python()
    print()

    # [2/4] 创建虚拟环境
    print("  [2/4] 创建虚拟环境")
    _create_venv()
    print()

    # 确定 pip 命令
    using_uv = _has_uv()
    if using_uv:
        pip_base = ["uv", "pip"]
    else:
        pip_base = _get_pip_cmd()
        # 原生 pip：先升级 pip
        print("  ⬆️  升级 pip...")
        _run_pip(pip_base + ["install", "--upgrade", "pip"])
        print()

    # [3/4] 安装核心依赖
    print("  [3/4] 安装核心依赖")
    reqs = [REQ_FILE]
    if args.dev or args.all:
        if REQ_DEV_FILE.exists():
            reqs.append(REQ_DEV_FILE)
    success = _install_using(pip_base, reqs)
    if not success:
        print()
        print("=" * 50)
        print("  ❌ 安装失败")
        print("=" * 50)
        print()
        print("  请检查网络后重试：python install.py")
        print()
        sys.exit(1)
    print()

    # [4/4] 可选依赖
    print("  [4/4] 可选依赖")
    install_count = 0
    if args.all:
        _install_optional(pip_base, "向量记忆（语义搜索）", "sentence-transformers")
        install_count += 1
    else:
        if _prompt_yes_no("是否安装向量记忆？（语义搜索，提升记忆质量）", default=False):
            _install_optional(pip_base, "向量记忆", "sentence-transformers")
            install_count += 1

    print()

    # 完成
    print("=" * 50)
    print("  ✅ 安装完成！")
    print("=" * 50)
    print()
    print("  接下来运行：")
    print("    python main.py setup   # 配置模型和人设")
    print("    python main.py         # 开始聊天")
    if args.dev:
        print("    python -m pytest tests/ -v  # 运行测试")
    print()

    # 提示未激活虚拟环境
    if not using_uv and sys.prefix == sys.base_prefix:
        print("  ! 注意：依赖已安装到 .venv，启动前请激活：")
        if sys.platform == "win32":
            print("    .venv\\Scripts\\activate.bat")
        else:
            print("    source .venv/bin/activate")
        print("    或直接运行 python main.py（从项目根目录）")
        print()


def _prompt_yes_no(msg: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    val = input(f"  {msg} ({hint}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes", "是")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  安装已取消")
    except Exception as e:
        print(f"\n  ❌ 安装出错: {e}")
        import traceback
        traceback.print_exc()

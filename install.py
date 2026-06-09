"""环境安装脚本

创建虚拟环境并使用国内镜像安装依赖。
用法：python install.py
"""

import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).parent
VENV_DIR = ROOT / ".venv"
REQ_FILE = ROOT / "requirements.txt"

# 国内镜像源（按优先级排列）
MIRRORS = [
    ("清华", "https://pypi.tuna.tsinghua.edu.cn/simple"),
    ("阿里", "https://mirrors.aliyun.com/pypi/simple"),
    ("中科大", "https://pypi.mirrors.ustc.edu.cn/simple"),
    ("官方", "https://pypi.org/simple"),
]

PYTHON_MIN = (3, 11)


def _check_python():
    """检查 Python 版本"""
    v = sys.version_info[:2]
    if v < PYTHON_MIN:
        print(f"  ❌ 需要 Python {PYTHON_MIN[0]}.{PYTHON_MIN[1]}+，当前 {v[0]}.{v[1]}")
        print(f"     请前往 https://www.python.org/downloads/ 下载")
        sys.exit(1)
    print(f"  ✅ Python {v[0]}.{v[1]}")


def _create_venv():
    """创建虚拟环境"""
    if VENV_DIR.exists():
        print(f"  📁 虚拟环境已存在: {VENV_DIR}")
        ans = input("  是否重建？(y/N): ").strip().lower()
        if ans != "y":
            print("  跳过创建，使用现有环境")
            return
        import shutil
        shutil.rmtree(VENV_DIR)
        print("  🗑️  已删除旧环境")

    print("  🔧 创建虚拟环境...")
    subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR)],
        check=True,
    )
    print(f"  ✅ 虚拟环境创建成功: {VENV_DIR}")


def _get_pip():
    """获取 venv 中的 pip 路径"""
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "pip.exe"
    return VENV_DIR / "bin" / "pip"


def _install_deps():
    """用国内镜像安装依赖"""
    pip = _get_pip()
    if not pip.exists():
        print(f"  ❌ 找不到 pip: {pip}")
        sys.exit(1)

    if not REQ_FILE.exists():
        print(f"  ❌ 找不到 requirements.txt: {REQ_FILE}")
        sys.exit(1)

    print("  📦 安装依赖...\n")

    for name, url in MIRRORS:
        print(f"  尝试源: {name} ({url})")
        result = subprocess.run(
            [str(pip), "install", "-r", str(REQ_FILE), "-i", url],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"\n  ✅ 依赖安装成功！（使用 {name} 源）")
            return True
        else:
            # 只显示最后几行错误
            err_lines = result.stderr.strip().split("\n")
            print(f"  ❌ {name} 源失败: {err_lines[-1] if err_lines else '未知错误'}")
            print()

    print("  ❌ 所有镜像源都失败了，请检查网络连接")
    print("  你可以手动尝试：")
    print(f"    {pip} install -r {REQ_FILE} -i https://pypi.tuna.tsinghua.edu.cn/simple")
    return False


def main():
    print()
    print("=" * 50)
    print("  🎀 赛博女友 - 环境安装")
    print("=" * 50)
    print()

    print("  [1/3] 检查 Python 版本")
    _check_python()
    print()

    print("  [2/3] 创建虚拟环境")
    _create_venv()
    print()

    print("  [3/3] 安装依赖")
    success = _install_deps()
    print()

    if success:
        print("=" * 50)
        print("  ✅ 安装完成！")
        print("=" * 50)
        print()
        print("  接下来运行：")
        print("    python main.py setup   # 配置模型和人设")
        print("    python main.py         # 开始聊天")
        print()
        print("  或者双击 start.bat 直接启动")
        print()
    else:
        print("=" * 50)
        print("  ❌ 安装失败")
        print("=" * 50)
        print()
        print("  请检查网络后重试：python install.py")
        print()
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  安装已取消")
    except Exception as e:
        print(f"\n  ❌ 安装出错: {e}")
        import traceback
        traceback.print_exc()

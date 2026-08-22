# 便携发行包

便携包不修改系统注册表，也不要求用户预先安装 Python。构建器接收一个
自包含的运行时目录，因此不同平台只需要替换 runtime 和启动脚本：

```text
Mu/
├─ app/       # 跨平台应用代码和 Web 资源
├─ runtime/   # 发布流水线提供的自包含 Python 运行时
├─ userdata/  # 首次启动生成，聊天记录和配置都在这里
└─ 启动慕.cmd / start.sh
```

构建示例：

```powershell
python scripts/prepare_windows_runtime.py --output build/windows-runtime
python scripts/build_portable.py --runtime-dir build/windows-runtime --output dist --target-platform windows
python scripts/smoke_test_portable.py dist/Mu-4.3.0-portable.zip
```

发布流水线应先下载并缓存核心 wheel，再使用 `--wheelhouse` 构建运行时；
这样正式出包不依赖某一个国内镜像的实时可用性。
Python 嵌入式运行时会缓存到 `build/downloads`，默认先尝试国内镜像再回退官方源；
也可以通过 `--python-archive` 使用已经下载好的 ZIP。

`runtime-dir` 不能是开发机的普通 `.venv`，应由 Windows、Linux 或 macOS
发布流水线分别准备。构建器不关心宿主平台，也不会把路径写死在核心代码里。
Linux/macOS 运行时必须提供 `runtime/bin/python`，Windows 运行时必须提供
`runtime/python.exe`；构建器会在出包前校验，并把目标平台写入 `portable.json`。

"""Web UI 后端 — aiohttp 网页服务

在同进程内复用已初始化的 AppComponents（pipeline / vision / registry），
提供：
- GET  /                 静态页面
- GET  /api/schema       设置字段定义（前端动态渲染）
- GET  /api/settings     当前设置有效值
- POST /api/settings     写入设置并热更新到运行中的实例
- POST /api/chat         流式对话（SSE）
- POST /api/upload/image 图片上传 + 识别
- POST /api/upload/voice 语音上传（可选 ASR，未配置则优雅降级）

不修改核心业务逻辑，仅作为一层适配。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

from loguru import logger

from core.config import ROOT, CONFIG_DIR, DEFAULT_PERSONA_ID, load_advanced
from .schema import SETTINGS_SCHEMA, coerce_value

STATIC_DIR = Path(__file__).resolve().parent / "static"
UPLOAD_DIR = ROOT / "data" / "uploads"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

WEB_USER_ID = "web_user"


# ────────── 设置读写 ──────────

def _load_settings() -> dict:
    """读取 settings.json，缺失返回空 dict。"""
    if SETTINGS_PATH.exists():
        try:
            return json.loads(SETTINGS_PATH.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"WebUI: failed to read settings.json: {e}")
    return {}


def _save_settings(settings: dict) -> None:
    """原子写入 settings.json。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    tmp.replace(SETTINGS_PATH)


def _current_values() -> dict:
    """按 schema 汇总当前有效值：settings.json > load_advanced 默认 > schema 默认。"""
    settings = _load_settings()
    advanced = settings.get("advanced", {})
    models = settings.get("models", {})
    default_model = settings.get("default_model")
    model_cfg = models.get(default_model, {}) if default_model else {}
    # 任取一个模型兜底（default 未设时）
    if not model_cfg and models:
        model_cfg = next(iter(models.values()))

    fallback_advanced = load_advanced()
    values: dict = {}
    for field in SETTINGS_SCHEMA:
        key = field["key"]
        target = field["target"]
        default = field["default"]
        if target == "model":
            values[key] = model_cfg.get(key, default)
        elif target == "model_repetition":
            # presence/frequency 合并展示，取 presence 为准
            values[key] = model_cfg.get("presence_penalty", default)
        else:  # advanced
            values[key] = advanced.get(key, fallback_advanced.get(key, default))
        values[key] = coerce_value(field, values[key])
    return values


def _persist_values(values: dict) -> None:
    """把 schema 值写回 settings.json 的正确位置。"""
    settings = _load_settings()
    advanced = settings.setdefault("advanced", {})
    models = settings.setdefault("models", {})
    default_model = settings.get("default_model")
    targets = [models[default_model]] if default_model and default_model in models else list(models.values())

    for field in SETTINGS_SCHEMA:
        key = field["key"]
        target = field["target"]
        val = values.get(key)
        if val is None:
            continue
        if target == "model":
            for m in targets:
                m[key] = val
        elif target == "model_repetition":
            for m in targets:
                m["presence_penalty"] = val
                m["frequency_penalty"] = val
        else:
            advanced[key] = val
    _save_settings(settings)


def _apply_live(app, values: dict) -> None:
    """热更新到运行中的实例，避免重启。"""
    # 1. 模型参数 → 直接改 LLM 实例属性
    try:
        llm = app.registry.get() if app.registry.available_models else None
    except Exception:
        llm = None
    if llm is not None:
        if "temperature" in values:
            llm.temperature = values["temperature"]
        if "max_tokens" in values:
            llm.max_tokens = values["max_tokens"]
        if "max_retries" in values:
            llm.max_retries = values["max_retries"]
        if "repetition_penalty" in values:
            llm.presence_penalty = values["repetition_penalty"]
            llm.frequency_penalty = values["repetition_penalty"]

    # 2. advanced 参数 → 更新共享 config dict
    cfg = getattr(app, "advanced_config", None)
    if isinstance(cfg, dict):
        for key in ("segment_max_length", "debounce_seconds", "summarize_threshold",
                    "proactive_enabled", "proactive_active_start", "proactive_active_end",
                    "proactive_interval_min", "proactive_interval_max"):
            if key in values:
                cfg[key] = values[key]

    # 3. 主动消息开关热更新
    if hasattr(app, "proactive") and app.proactive is not None:
        if "proactive_enabled" in values:
            app.proactive.enabled = values["proactive_enabled"]


# ────────── HTTP handlers ──────────

def _make_app(app_components):
    from aiohttp import web

    routes = web.RouteTableDef()

    @routes.get("/")
    async def index(_request):
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return web.FileResponse(index_file)
        return web.Response(
            text="webui/static/index.html 尚未生成", status=404
        )

    @routes.get("/api/schema")
    async def get_schema(_request):
        return web.json_response({"schema": SETTINGS_SCHEMA})

    @routes.get("/api/settings")
    async def get_settings(_request):
        return web.json_response({"values": _current_values()})

    @routes.post("/api/settings")
    async def post_settings(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        incoming = body.get("values", body) or {}
        clean: dict = {}
        for field in SETTINGS_SCHEMA:
            key = field["key"]
            if key in incoming:
                clean[key] = coerce_value(field, incoming[key])

        if not clean:
            return web.json_response({"error": "no valid fields"}, status=400)

        try:
            _persist_values(clean)
            _apply_live(app_components, clean)
        except Exception as e:
            logger.error(f"WebUI: apply settings failed: {e}")
            return web.json_response({"error": str(e)}, status=500)

        return web.json_response({"ok": True, "values": _current_values()})

    @routes.post("/api/chat")
    async def chat(request):
        try:
            body = await request.json()
        except Exception:
            return web.json_response({"error": "invalid JSON"}, status=400)

        content = (body.get("content") or "").strip()
        if not content:
            return web.json_response({"error": "content is required"}, status=400)
        user_id = body.get("user_id") or WEB_USER_ID

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_token(token: str):
            loop.call_soon_threadsafe(queue.put_nowait, token)

        pipeline = app_components.handler.pipeline

        async def _run():
            try:
                reply, level = await pipeline.process(
                    user_id, content, DEFAULT_PERSONA_ID, on_token=on_token,
                )
                return reply, level
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        task = asyncio.create_task(_run())

        async def _send(event: str, data: dict):
            payload = json.dumps(data, ensure_ascii=False)
            await response.write(
                f"event: {event}\ndata: {payload}\n\n".encode("utf-8")
            )

        try:
            while True:
                token = await queue.get()
                if token is None:
                    break
                await _send("token", {"token": token})
            reply, level = await task
            await _send("done", {"reply": reply, "level": level})
        except Exception as e:
            logger.error(f"WebUI chat error: {e}")
            try:
                await _send("error", {"error": str(e)})
            except Exception:
                pass
        finally:
            if not task.done():
                task.cancel()
            try:
                await response.write_eof()
            except Exception:
                pass
        return response

    @routes.post("/api/upload/image")
    async def upload_image(request):
        vision = getattr(app_components, "vision_manager", None)
        pipeline = app_components.handler.pipeline

        reader = await request.multipart()
        image_path = None
        caption = ""
        user_id = WEB_USER_ID
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        async for part in reader:
            if part.name == "image":
                ext = Path(part.filename or "img.png").suffix or ".png"
                image_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
                with open(image_path, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)
            elif part.name == "caption":
                caption = (await part.text()).strip()
            elif part.name == "user_id":
                user_id = (await part.text()).strip() or WEB_USER_ID

        if image_path is None:
            return web.json_response({"error": "no image"}, status=400)

        if vision is None:
            return web.json_response(
                {"error": "视觉识别未配置"}, status=400
            )

        try:
            vision_prompt = (
                "请客观描述这张图片的内容：画面里有什么、是什么场景、"
                "有什么值得注意的细节。只描述事实，不要加表情、语气和评价。"
            )
            vision_result = await vision.process(str(image_path), vision_prompt)
            if vision.main_is_multimodal:
                reply = vision_result
            else:
                enhanced = vision.build_enhanced_message(vision_result, caption)
                reply, _ = await pipeline.process(
                    user_id, enhanced, DEFAULT_PERSONA_ID,
                )
            return web.json_response({"reply": reply})
        except Exception as e:
            logger.error(f"WebUI image error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    @routes.post("/api/upload/voice")
    async def upload_voice(request):
        """语音上传：若配置了 ASR 则转写为文本再走对话，否则优雅降级。"""
        pipeline = app_components.handler.pipeline
        reader = await request.multipart()
        audio_path = None
        user_id = WEB_USER_ID
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        async for part in reader:
            if part.name == "audio":
                ext = Path(part.filename or "voice.webm").suffix or ".webm"
                audio_path = UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
                with open(audio_path, "wb") as f:
                    while True:
                        chunk = await part.read_chunk()
                        if not chunk:
                            break
                        f.write(chunk)
            elif part.name == "user_id":
                user_id = (await part.text()).strip() or WEB_USER_ID

        if audio_path is None:
            return web.json_response({"error": "no audio"}, status=400)

        text = _try_transcribe(audio_path)
        if not text:
            return web.json_response(
                {"error": "语音转写未配置", "need_asr": True}, status=400
            )
        try:
            reply, _ = await pipeline.process(user_id, text, DEFAULT_PERSONA_ID)
            return web.json_response({"transcript": text, "reply": reply})
        except Exception as e:
            logger.error(f"WebUI voice error: {e}")
            return web.json_response({"error": str(e)}, status=500)

    aio_app = web.Application(client_max_size=32 * 1024 * 1024)
    aio_app.add_routes(routes)
    if STATIC_DIR.exists():
        aio_app.router.add_static("/static/", STATIC_DIR, name="static")
    return aio_app


def _try_transcribe(audio_path: Path) -> str | None:
    """尝试用 faster-whisper 转写；未安装则返回 None（优雅降级）。"""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception:
        return None
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), language="zh")
        return "".join(seg.text for seg in segments).strip() or None
    except Exception as e:
        logger.warning(f"WebUI ASR failed: {e}")
        return None


async def run_web(app_components, host: str = "127.0.0.1", port: int = 8000) -> None:
    """启动网页服务（阻塞直到取消）。"""
    from aiohttp import web

    aio_app = _make_app(app_components)
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    # 连接 MCP 工具（可选）
    mcp = getattr(app_components, "mcp_manager", None)
    if mcp is not None:
        try:
            connected = await mcp.load_and_connect(CONFIG_DIR)
            if connected:
                logger.info(f"WebUI: MCP {connected} server(s) connected")
        except Exception as e:
            logger.warning(f"WebUI: MCP connect failed: {e}")

    url = f"http://{host}:{port}"
    print(f"\n  🌐 网页端已启动：{url}")
    print(f"  浏览器打开上面的地址即可对话 + 调参")
    print(f"  按 Ctrl+C 停止\n")
    logger.info(f"WebUI running on {url}")

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()

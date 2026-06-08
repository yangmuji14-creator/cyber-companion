"""WebUI 后端 API"""

import json
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent.parent
CONFIG_DIR = ROOT / "config"
STATIC_DIR = Path(__file__).parent / "static"


def create_webui_app(registry, memory_mgr, persona_loader) -> FastAPI:
    """创建 WebUI FastAPI 应用"""

    app = FastAPI(title="Cyber Girlfriend WebUI", docs_url="/api/docs")

    # 挂载静态文件
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # ========== 页面路由 ==========

    @app.get("/", response_class=HTMLResponse)
    async def index():
        """主页"""
        return FileResponse(str(STATIC_DIR / "index.html"))

    # ========== 健康检查 ==========

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "models": registry.available_models,
            "default_model": registry.default_model,
            "personas": [p.id for p in persona_loader.list_all()],
        }

    # ========== 账户管理 ==========

    @app.get("/api/accounts")
    async def list_accounts():
        """列出所有账户"""
        config_path = CONFIG_DIR / "accounts.json"
        if not config_path.exists():
            return {"accounts": []}
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @app.post("/api/accounts")
    async def add_account(request: Request):
        """添加账户"""
        data = await request.json()
        config_path = CONFIG_DIR / "accounts.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        config["accounts"].append(data)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return {"status": "ok", "account": data}

    @app.delete("/api/accounts/{account_id}")
    async def delete_account(account_id: str):
        """删除账户"""
        config_path = CONFIG_DIR / "accounts.json"

        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        config["accounts"] = [a for a in config["accounts"] if a.get("id") != account_id]

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        return {"status": "ok"}

    # ========== 人设管理 ==========

    @app.get("/api/personas")
    async def list_personas():
        """列所有人设"""
        personas = persona_loader.list_all()
        return {"personas": [p.to_dict() for p in personas]}

    @app.get("/api/personas/{persona_id}")
    async def get_persona(persona_id: str):
        """获取人设详情"""
        persona = persona_loader.get(persona_id)
        if not persona:
            return {"error": "not found"}
        return persona.to_dict()

    @app.post("/api/personas")
    async def create_persona(request: Request):
        """创建人设"""
        from core.persona import Persona
        data = await request.json()
        persona = Persona.from_dict(data)
        persona_loader.add(persona)
        return {"status": "ok", "persona": persona.to_dict()}

    @app.put("/api/personas/{persona_id}")
    async def update_persona(persona_id: str, request: Request):
        """更新人设"""
        data = await request.json()
        persona = persona_loader.update(persona_id, **data)
        if not persona:
            return {"error": "not found"}
        return {"status": "ok", "persona": persona.to_dict()}

    @app.delete("/api/personas/{persona_id}")
    async def delete_persona(persona_id: str):
        """删除人设"""
        ok = persona_loader.delete(persona_id)
        return {"status": "ok" if ok else "not found"}

    # ========== 记忆管理 ==========

    @app.get("/api/memories/{user_id}")
    async def list_memories(user_id: str, limit: int = 50):
        """列出用户记忆"""
        memories = memory_mgr.get_memories(user_id, limit=limit)
        return {
            "user_id": user_id,
            "memories": [m.to_dict() for m in memories],
            "total": len(memory_mgr._storage.load(user_id)),
        }

    @app.get("/api/memories")
    async def list_all_users():
        """列出所有有记忆的用户"""
        users = memory_mgr._storage.list_users()
        result = []
        for uid in users:
            memories = memory_mgr._storage.load(uid)
            result.append({
                "user_id": uid,
                "count": len(memories),
                "top_level": max((m.level for m in memories), default=0),
            })
        return {"users": result}

    @app.post("/api/memories/{user_id}")
    async def add_memory(user_id: str, request: Request):
        """手动添加记忆"""
        data = await request.json()
        content = data.get("content", "")
        level = data.get("level")
        tags = data.get("tags", [])
        memory = memory_mgr.add_memory(user_id, content, level=level, tags=tags)
        if memory:
            return {"status": "ok", "memory": memory.to_dict()}
        return {"error": "memory not important enough"}

    @app.delete("/api/memories/{user_id}/{memory_id}")
    async def delete_memory(user_id: str, memory_id: str):
        """删除记忆"""
        ok = memory_mgr.delete_memory(user_id, memory_id)
        return {"status": "ok" if ok else "not found"}

    @app.delete("/api/memories/{user_id}")
    async def delete_all_memories(user_id: str):
        """删除用户所有记忆"""
        ok = memory_mgr._storage.delete_all(user_id)
        return {"status": "ok" if ok else "not found"}

    @app.get("/api/memories/{user_id}/export")
    async def export_memories(user_id: str):
        """导出用户记忆"""
        memories = memory_mgr.export_memories(user_id)
        return {"user_id": user_id, "memories": memories}

    # ========== 模型管理 ==========

    @app.get("/api/models")
    async def list_models():
        """列出可用模型"""
        return {
            "models": registry.available_models,
            "default": registry.default_model,
        }

    @app.post("/api/models/default")
    async def set_default_model(request: Request):
        """设置默认模型"""
        data = await request.json()
        model_name = data.get("model")
        if model_name not in registry.available_models:
            return {"error": "model not found"}
        registry._default_model = model_name
        return {"status": "ok", "default": model_name}

    # ========== 聊天测试 ==========

    @app.post("/api/chat")
    async def chat(request: Request):
        """聊天测试"""
        data = await request.json()
        user_id = data.get("user_id", "web_user")
        content = data.get("content", "")
        if not content:
            return {"error": "content required"}

        # 延迟导入避免循环依赖
        from main import handle_message
        reply = await handle_message(user_id, content)
        return {"reply": reply}

    return app

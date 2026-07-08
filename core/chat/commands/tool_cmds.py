"""工具 / 图片 / 导出 / 重新生成命令：/tools, /img, /export, /regen"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from core.chat.commands.colors import Colors
from core.multimodal import ImageHandler


def cmd_tools(handler) -> None:
    """查看可用工具列表（含 MCP 工具）"""
    # 内置工具
    tr = getattr(handler._h, '_tool_registry', None)
    builtin_count = 0
    if tr and tr.available:
        print(f"\n{Colors.YELLOW}🛠️ 内置工具{Colors.RESET}")
        for tool in tr.list_tools():
            params = tool.parameters
            props = params.get("properties", {})
            param_str = ", ".join(props.keys()) if props else "无参数"
            print(f"  {Colors.CYAN}{tool.name}{Colors.RESET} — {tool.description}")
            print(f"    参数：{param_str}")
            builtin_count += 1

    # MCP 工具
    mcp = getattr(handler._h, '_mcp_manager', None)
    mcp_count = 0
    if mcp and mcp.tools_count > 0:
        print(f"\n{Colors.YELLOW}🔌 MCP 扩展工具{Colors.RESET}")
        for tool in mcp.get_all_tools():
            props = tool.parameters.get("properties", {})
            param_str = ", ".join(props.keys()) if props else "无参数"
            print(f"  {Colors.CYAN}{tool.name}{Colors.RESET} [{tool.server_name}] — {tool.description}")
            print(f"    参数：{param_str}")
            mcp_count += 1

    if builtin_count == 0 and mcp_count == 0:
        print(f"\n{Colors.DIM}  没有可用工具{Colors.RESET}\n")
    else:
        print()


async def cmd_img(handler, user_id: str, cmd: str) -> None:
    """处理 /img 命令：发送图片给 AI 识别（双路径）"""
    img_handler = ImageHandler()
    image_path, user_text = img_handler.parse_img_command(cmd)
    if not image_path:
        print(f"\n{Colors.YELLOW}📷 发送图片：{Colors.RESET}")
        print(f"  {Colors.CYAN}/img <图片路径> [文字说明]{Colors.RESET}")
        print(f"  {Colors.DIM}示例：/img C:\\photo.jpg 看看这个{Colors.RESET}")
        print(f"  {Colors.DIM}支持 jpg/png/gif/webp/bmp，最大 10MB{Colors.RESET}\n")
        return

    if not Path(image_path).exists():
        print(f"\n{Colors.DIM}  图片不存在：{image_path}{Colors.RESET}\n")
        return

    print(f"\n{Colors.YELLOW}📷 正在识别图片...{Colors.RESET}")

    # 使用 VisionManager 双路径处理
    vm = getattr(handler._h, '_vision_manager', None)

    if vm:
        result = await vm.process(image_path, user_text or "请描述这张图片的内容")
    else:
        # 降级：使用旧的 ImageHandler 方式
        loaded = img_handler.load_image(image_path)
        if not loaded:
            print(f"\n{Colors.DIM}  图片加载失败{Colors.RESET}\n")
            return
        b64_data, mime_type = loaded
        vision_messages = img_handler.build_vision_messages(b64_data, mime_type, user_text)
        vision_prompt = img_handler.get_vision_prompt()
        llm = getattr(handler._h, '_registry', None)
        if not llm or not llm.available_models:
            print(f"\n{Colors.DIM}  没有可用的模型{Colors.RESET}\n")
            return
        model = llm.get()
        try:
            response = await model.chat(
                messages=vision_messages, system_prompt=vision_prompt,
            )
            result = response.content
            # 暴力清空 litellm 全局状态
            try:
                import litellm
                litellm.api_key = None
                litellm.api_base = None
            except Exception:
                pass
        except Exception as e:
            logger.error(f"图片识别失败: {e}")
            print(f"\n{Colors.DIM}  图片识别失败{Colors.RESET}\n")
            return

    # 如果主模型不是多模态的（走降级路径），需要把描述 + 用户文字发给主模型
    if vm and not vm.main_is_multimodal:
        # 暴力恢复环境变量 + litellm 状态
        try:
            import litellm
            litellm.api_key = None
            litellm.api_base = None
        except Exception:
            pass
        try:
            from dotenv import load_dotenv
            load_dotenv(override=True)
        except Exception:
            pass

        enhanced = vm.build_enhanced_message(result, user_text or "")
        handler._h.chat_history.add_message(
            user_id, "user",
            f"[图片] {user_text}" if user_text else "[图片]",
        )
        # 作为 pipeline 消息发送
        from core.chat.display import spinner_task, print_reply_token, print_rel_change
        first_token = [True]
        spinner_stop = asyncio.Event()
        last_reply = [""]

        def _on_token(token: str):
            last_reply[0] += token
            if first_token[0]:
                spinner_stop.set()
                print_reply_token("AI", token, True)
                first_token[0] = False
            else:
                print_reply_token("AI", token, False)

        spinner = asyncio.create_task(spinner_task(spinner_stop, "AI"))
        reply, rel_level = await handler._h.pipeline.process(
            user_id, enhanced, handler._h.current_persona_id,
            on_token=_on_token, skip_user_message=True,
        )
        if not spinner_stop.is_set():
            spinner_stop.set()
        spinner.cancel()
        if first_token[0]:
            persona = handler._h.persona_loader.get(handler._h.current_persona_id)
            p_name = persona.name if persona else "AI"
            print(f"\n{Colors.MAGENTA}{p_name}:{Colors.RESET} {reply}")
        else:
            print()
        print_rel_change(rel_level)
        return

    # 多模态直传路径：结果就是最终回复
    handler._h.chat_history.add_message(
        user_id, "user",
        f"[图片] {user_text}" if user_text else "[图片]",
    )
    handler._h.chat_history.add_message(user_id, "assistant", result)
    persona = handler._h.persona_loader.get(handler._h.current_persona_id)
    p_name = persona.name if persona else "AI"
    print(f"\n{Colors.MAGENTA}{p_name}:{Colors.RESET} {result}\n")


async def cmd_export(handler, user_id: str, fmt: str) -> None:
    """导出聊天记录"""
    msgs = handler._h.chat_history.get_messages(user_id)
    if not msgs:
        print(f"\n{Colors.DIM}  没有可导出的聊天记录{Colors.RESET}\n")
        return

    persona = handler._h.persona_loader.get(handler._h.current_persona_id)
    persona_name = persona.name if persona else "AI"
    export_dir = Path(handler._h.chat_history.data_dir) / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    if fmt == "json":
        filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = export_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    else:
        filename = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        filepath = export_dir / filename
        md_content = handler._h.chat_history.export_markdown(user_id, persona_name)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md_content)

    print(f"\n{Colors.GREEN}✅ 已导出到 {filepath}{Colors.RESET}")
    print(f"  {Colors.DIM}格式：{'Markdown' if fmt != 'json' else 'JSON'}（用 /export json 或 /export md 切换）{Colors.RESET}\n")


async def cmd_regen(handler, user_id: str, persona_name: str) -> None:
    """让 AI 重新生成上一条回复"""
    msgs = handler._h.chat_history.get_messages(user_id)
    if not msgs:
        print(f"\n{Colors.DIM}  还没有对话记录{Colors.RESET}\n")
        return
    if msgs[-1]["role"] != "assistant":
        print(f"\n{Colors.YELLOW}⚠ 最后一条消息不是 AI 回复，无法重新生成{Colors.RESET}\n")
        return

    handler._h.chat_history.delete_last_messages(user_id, 1)
    user_msgs = [m for m in msgs if m["role"] == "user"]
    if not user_msgs:
        print(f"\n{Colors.YELLOW}⚠ 找不到对应的用户消息{Colors.RESET}\n")
        return

    last_user = user_msgs[-1]["content"]
    print(f"\n  {Colors.DIM}🔄 重新生成中...{Colors.RESET}")

    reply, rel_level = await handler._h.pipeline.process(
        user_id, last_user, handler._h.current_persona_id, skip_user_message=True,
    )
    p = handler._h.persona_loader.get(handler._h.current_persona_id)
    name = p.name if p else persona_name
    print(f"\r  {name}: {reply}\n")

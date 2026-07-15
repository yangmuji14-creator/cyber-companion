"""CommandHandler — 斜杠命令路由和执行器

将具体命令实现委托到子模块。
"""

from core.chat.commands import system_cmds
from core.chat.commands import stats_cmds
from core.chat.commands import memory_cmds
from core.chat.commands import persona_cmds
from core.chat.commands import tool_cmds
from loguru import logger


class CommandHandler:
    """斜杠命令路由和执行器"""

    def __init__(self, handler: "ChatHandler"):
        self._h = handler  # ChatHandler 实例引用

    async def handle(self, cmd: str, user_id: str, persona_name: str):
        """处理一条斜杠命令，返回 True=已处理 / False=不是命令 / "quit"=退出"""
        cmd = cmd.strip().lower()

        try:
            if cmd == "/help":
                system_cmds.cmd_help(self)
                return True

            if cmd.startswith("/stats"):
                await stats_cmds.cmd_stats(self, cmd, user_id)
                return True

            if cmd.startswith("/memories"):
                parts = cmd.split(maxsplit=1)
                sub = parts[1].strip() if len(parts) > 1 else "list"
                await memory_cmds.cmd_memories(self, user_id, sub)
                return True

            if cmd in ("/persona", "/personality") or cmd.startswith("/persona ") or cmd.startswith("/personality "):
                if cmd.startswith("/personality"):
                    persona_cmds.cmd_personality(self, user_id)
                    return True
                parts = cmd.split(maxsplit=1)
                sub = parts[1].strip() if len(parts) > 1 else ""
                persona_cmds.cmd_persona(self, user_id, sub)
                return True

            if cmd == "/clear" or cmd == "/clear --confirm":
                system_cmds.cmd_clear(self, user_id, cmd)
                return True

            if cmd == "/debug":
                system_cmds.cmd_debug(self)
                return True

            if cmd.startswith("/export"):
                parts = cmd.split(maxsplit=1)
                fmt = parts[1].strip() if len(parts) > 1 else "md"
                await tool_cmds.cmd_export(self, user_id, fmt)
                return True

            if cmd == "/undo":
                system_cmds.cmd_undo(self, user_id)
                return True

            if cmd == "/regen":
                await tool_cmds.cmd_regen(self, user_id, persona_name)
                return True

            if cmd.startswith("/search"):
                keyword = cmd[8:].strip() if len(cmd) > 7 else ""
                memory_cmds.cmd_search(self, user_id, keyword)
                return True

            if cmd == "/mood":
                persona_cmds.cmd_mood(self, user_id)
                return True

            if cmd == "/tools":
                tool_cmds.cmd_tools(self)
                return True

            if cmd.startswith("/img"):
                await tool_cmds.cmd_img(self, user_id, cmd)
                return True

            if cmd == "/quit":
                return "quit"

            return False
        except Exception:
            logger.error("Command failed")
            print("这个命令暂时没能完成，稍后再试一次吧。")
            return True

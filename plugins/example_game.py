"""示例插件 — 展示插件系统用法

这是一个简单的游戏插件示例，展示如何：
1. 继承 Plugin 基类
2. 处理用户消息
3. 提供斜杠命令
4. 修改 AI 回复
"""

from plugins.base import Plugin, PluginContext, PluginResult


class GamePlugin(Plugin):
    """游戏插件：提供简单的猜数字游戏"""

    name = "game"
    description = "猜数字游戏插件"
    version = "1.0.0"
    author = "Cyber Girlfriend"

    def __init__(self):
        super().__init__()
        self._games: dict[str, dict] = {}  # user_id -> game_state

    def get_commands(self) -> dict[str, str]:
        return {
            "/game": "开始猜数字游戏（1-100）",
            "/guess": "猜测一个数字，格式：/guess 50",
            "/game_end": "结束当前游戏",
        }

    async def handle_command(self, command: str, args: str, context: PluginContext) -> PluginResult:
        import random

        if command == "/game":
            # 开始新游戏
            target = random.randint(1, 100)
            self._games[context.user_id] = {
                "target": target,
                "attempts": 0,
                "max_attempts": 7,
            }
            return PluginResult(
                success=True,
                response=f"🎮 猜数字游戏开始！\n我想了一个 1-100 的数字，你有 7 次机会猜它。\n用 /guess 数字 来猜测！",
                action="reply",
            )

        elif command == "/guess":
            if context.user_id not in self._games:
                return PluginResult(success=True, response="先用 /game 开始游戏哦~")

            game = self._games[context.user_id]
            try:
                guess = int(args.strip())
            except ValueError:
                return PluginResult(success=True, response="请输入一个数字，比如 /guess 50")

            game["attempts"] += 1
            target = game["target"]
            remaining = game["max_attempts"] - game["attempts"]

            if guess == target:
                del self._games[context.user_id]
                return PluginResult(
                    success=True,
                    response=f"🎉 猜对了！就是 {target}！\n你用了 {game['attempts']} 次猜中，{self._get_rating(game['attempts'])}",
                )
            elif guess < target:
                hint = f"小了~ 还剩 {remaining} 次机会"
            else:
                hint = f"大了~ 还剩 {remaining} 次机会"

            if remaining <= 0:
                del self._games[context.user_id]
                return PluginResult(
                    success=True,
                    response=f"😢 游戏结束！答案是 {target}，再接再厉~",
                )

            return PluginResult(success=True, response=hint)

        elif command == "/game_end":
            if context.user_id in self._games:
                target = self._games[context.user_id]["target"]
                del self._games[context.user_id]
                return PluginResult(success=True, response=f"游戏已结束~ 答案是 {target}")
            return PluginResult(success=True, response="当前没有进行中的游戏")

        return PluginResult(success=False)

    def _get_rating(self, attempts: int) -> str:
        if attempts <= 3:
            return "太厉害了！🏆"
        elif attempts <= 5:
            return "很不错！👍"
        else:
            return "刚好猜中~ 😊"

    async def on_message(self, context: PluginContext) -> PluginResult | None:
        """不主动处理消息，只通过命令触发"""
        return None

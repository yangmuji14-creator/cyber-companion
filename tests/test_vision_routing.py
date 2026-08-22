from pathlib import Path
from types import SimpleNamespace

import pytest

from adapters.wechat import WeChatAdapter
import adapters.wechat as wechat_module
from core.multimodal.vision import VisionManager, is_multimodal_model


class _MultimodalModel:
    model_name = "gpt-4.1-mini"

    def __init__(self, reply="看到了晚霞"):
        self.reply = reply
        self.messages = None

    async def chat(self, *, messages):
        self.messages = messages
        return SimpleNamespace(content=self.reply)


def _image(tmp_path: Path) -> Path:
    path = tmp_path / "image.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n")
    return path


def test_recent_multimodal_model_names():
    assert is_multimodal_model("gpt-4.1-mini")
    assert is_multimodal_model("o4-mini")
    assert is_multimodal_model("gemini-2.5-flash")
    assert not is_multimodal_model("deepseek-chat")


async def test_multimodal_main_model_receives_image_content(tmp_path):
    model = _MultimodalModel()
    manager = VisionManager(main_model=model, vision_config={})
    result = await manager.process(_image(tmp_path), "看看这张图")
    assert result == "看到了晚霞"
    content = model.messages[0]["content"]
    assert content[0] == {"type": "text", "text": "看看这张图"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


async def test_direct_vision_failure_without_fallback_is_user_facing(tmp_path):
    class FailingModel(_MultimodalModel):
        async def chat(self, *, messages):
            raise RuntimeError("provider failed")

    manager = VisionManager(main_model=FailingModel(), vision_config={})
    result = await manager.process(_image(tmp_path), "看看")
    assert "主模型暂时无法读取" in result


async def test_wechat_multimodal_image_does_not_enter_pending_wait(tmp_path, monkeypatch):
    replies = []
    monkeypatch.setattr(wechat_module, "DATA_DIR", tmp_path)

    class Message:
        from_user = "wxid_test"
        message_id = "image-1"
        context_token = "token"

        def save(self, path):
            Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")

        def reply_text(self, text):
            replies.append(text)

    adapter = WeChatAdapter(account_id="test", main_model=_MultimodalModel("这是你发来的图片"))
    await adapter._on_image_message(Message())
    assert replies == ["这是你发来的图片"]
    assert adapter._pending_vision == {}

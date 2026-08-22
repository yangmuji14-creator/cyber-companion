import zipfile

import pytest

from core.multimodal.stickers import StickerService


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_sticker_service_imports_emotion_folders_and_resolves_safely(tmp_path):
    archive = tmp_path / "pack.zip"
    _zip(archive, {
        "happy/a.png": b"png",
        "sad/b.webp": b"webp",
        "notes.txt": b"ignored",
    })
    service = StickerService(tmp_path)

    result = service.import_zip(archive, "my-pack")

    assert result == {"pack": "my-pack", "images": 2}
    assert service.resolve("my-pack", "happy", "a.png").read_bytes() == b"png"
    assert len(service.list_stickers()) == 2


def test_sticker_service_rejects_traversal_and_ignores_zip_slip(tmp_path):
    archive = tmp_path / "pack.zip"
    _zip(archive, {
        "../outside.png": b"bad",
        "happy/good.png": b"good",
    })
    service = StickerService(tmp_path)

    result = service.import_zip(archive, "safe")

    assert result["images"] == 1
    assert not (tmp_path / "outside.png").exists()
    with pytest.raises(ValueError):
        service.resolve("..", "happy", "good.png")


def test_sticker_service_maps_mood_to_matching_group(tmp_path):
    builtins = tmp_path / "builtins"
    (builtins / "happy").mkdir(parents=True)
    (builtins / "happy" / "one.png").write_bytes(b"png")
    service = StickerService(tmp_path / "data", builtins)

    sticker = service.choose("ecstatic")

    assert sticker == {
        "pack": "builtin",
        "emotion": "happy",
        "filename": "one.png",
        "url": "/api/stickers/file/builtin/happy/one.png",
    }

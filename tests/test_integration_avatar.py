"""T12 Integration: persona avatar upload/delete full lifecycle.

Verifies the avatar upload → list → GET image → delete → cleared flow
end-to-end through the real HTTP routes (T2). Uses the api fixture
pattern from test_webui.py with isolated tmp_path for AVATAR_DIR.

Flows covered (per T12 plan):
1. Full lifecycle: upload PNG → GET /api/persona shows URL → GET /avatars/X.png
   serves the bytes → DELETE → GET /api/persona shows "" (cleared) →
   GET /avatars/X.png 404.
2. Re-upload with different extension: upload PNG → upload JPG → only
   JPG file remains (orphan cleanup within upload handler, T2 lesson #1).
3. DELETE is idempotent: second DELETE on same persona returns 200,
   no file to clean up.

SKIPPED flow (documented):
- Persona delete (PersonaLoader.delete) → avatar file orphan cleanup:
  this is T13's feature. The current PersonaLoader.delete (core/persona/
  loader.py:118-124) only removes the persona from the in-memory dict
  and re-saves personas.json — it does NOT touch the avatar file. T13
  is supposed to add avatar orphan cleanup to PersonaLoader.delete.
  T12 is test-only and MUST NOT modify loader.py, so this test documents
  the gap and verifies the current (pre-T13) behavior. When T13 merges,
  this test should be updated to assert the avatar file IS removed.

Privacy: no real images. Uses inline 67-byte 1x1 PNG (_PNG_1X1) and a
minimal JPEG. No external files, no network.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
import pytest
from aiohttp.test_utils import TestClient, TestServer

import webui.server as srv
from core.persona.models import Persona

from tests.test_webui import FakeAppComponents


# ════════════════════════════════════════════════════════════════
# Inline test images (privacy-safe, no external files)
# ════════════════════════════════════════════════════════════════

# Minimal valid 1x1 PNG (67 bytes) — same constant as test_webui.py.
_PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)

# Minimal valid 1x1 JPEG (107 bytes). Tiny but parseable by browsers
# and accepted by the avatar route's content-type whitelist.
_JPEG_1X1 = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
    b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
    b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00\x0b"
    b"\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05"
    b"\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03"
    b"\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03"
    b"\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05"
    b"\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0"
    b"$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZcdefghip"
    b"qrstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97"
    b"\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6"
    b"\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5"
    b"\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2"
    b"\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00"
    b"\xfb\xff\xd9"
)


# ════════════════════════════════════════════════════════════════
# Fixture — isolated AVATAR_DIR + TestClient
# ════════════════════════════════════════════════════════════════


@pytest.fixture
async def avatar_api(monkeypatch, tmp_path):
    """Yield (TestClient, FakeAppComponents) with isolated AVATAR_DIR.

    Patches AVATAR_DIR before _make_app so add_static captures the
    tmp path (T2 lesson #3: patch before _make_app). Two personas are
    pre-loaded so routes can target them by id.
    """
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"default_model": "test-model", "advanced": {}}',
                             encoding="utf-8")
    monkeypatch.setattr(srv, "SETTINGS_PATH", settings_file)
    monkeypatch.setattr(srv, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(srv, "AVATAR_DIR", tmp_path / "avatars")

    components = FakeAppComponents()
    components.persona_loader.add_test_persona("gf001", "Girlfriend One")
    components.persona_loader.add_test_persona("gf002", "Girlfriend Two")

    app = srv._make_app(components)
    server = TestServer(app)
    cli = TestClient(server)
    await cli.start_server()
    try:
        yield cli, components, tmp_path
    finally:
        await cli.close()


def _png_form():
    """Build a multipart form with a PNG file."""
    form = aiohttp.FormData()
    form.add_field("file", _PNG_1X1, filename="avatar.png",
                   content_type="image/png")
    return form


def _jpeg_form():
    """Build a multipart form with a JPEG file."""
    form = aiohttp.FormData()
    form.add_field("file", _JPEG_1X1, filename="avatar.jpg",
                   content_type="image/jpeg")
    return form


# ════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════


async def test_avatar_full_lifecycle_upload_get_delete_cleared(avatar_api):
    """Full lifecycle: upload → list shows URL → GET image → delete → cleared.

    Single narrative covering all four T2 avatar endpoints in sequence:
    1. POST   /api/persona/gf001/avatar      → 200, avatar_url set
    2. GET    /api/persona                    → avatar field = "/avatars/gf001.png"
    3. GET    /avatars/gf001.png              → 200, image bytes match upload
    4. DELETE /api/persona/gf001/avatar       → 200
    5. GET    /api/persona                    → avatar field = "" (cleared)
    6. GET    /avatars/gf001.png              → 404 (file removed)
    """
    client, components, _tmp_path = avatar_api

    # 1. Upload PNG
    resp = await client.post("/api/persona/gf001/avatar", data=_png_form())
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert data["avatar_url"] == "/avatars/gf001.png"

    # Persona's avatar field updated via loader.update
    assert components.persona_loader.get("gf001").avatar == "/avatars/gf001.png"

    # 2. GET /api/persona reflects the avatar URL
    resp = await client.get("/api/persona")
    assert resp.status == 200
    personas = await resp.json()
    target = next(p for p in personas if p["id"] == "gf001")
    assert target["avatar"] == "/avatars/gf001.png"

    # 3. GET /avatars/gf001.png serves the exact uploaded bytes
    resp = await client.get("/avatars/gf001.png")
    assert resp.status == 200
    assert resp.headers.get("Content-Type", "").startswith("image/")
    body = await resp.read()
    assert body == _PNG_1X1

    # 4. DELETE clears the file + persona field
    resp = await client.delete("/api/persona/gf001/avatar")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True
    assert components.persona_loader.get("gf001").avatar == ""

    # 5. GET /api/persona now shows empty avatar
    resp = await client.get("/api/persona")
    personas = await resp.json()
    target = next(p for p in personas if p["id"] == "gf001")
    assert target["avatar"] == ""

    # 6. File gone → static route 404
    resp = await client.get("/avatars/gf001.png")
    assert resp.status == 404


async def test_avatar_reupload_different_extension_no_orphan(avatar_api):
    """Re-upload with different extension → only new file remains.

    T2 lesson #1: upload handler does `glob(f"{persona_id}.*")` + unlink
    before writing the new file, so changing PNG → JPG doesn't leave an
    orphaned .png file on disk.
    """
    client, components, tmp_path = avatar_api
    avatar_dir = tmp_path / "avatars"

    # Upload PNG first
    resp = await client.post("/api/persona/gf001/avatar", data=_png_form())
    assert resp.status == 200
    assert (avatar_dir / "gf001.png").exists()

    # Re-upload as JPEG
    resp = await client.post("/api/persona/gf001/avatar", data=_jpeg_form())
    assert resp.status == 200
    data = await resp.json()
    assert data["avatar_url"] == "/avatars/gf001.jpg"

    # PNG file removed (orphan cleanup); only JPG remains
    assert not (avatar_dir / "gf001.png").exists()
    assert (avatar_dir / "gf001.jpg").exists()

    # Persona field points to the new URL
    assert components.persona_loader.get("gf001").avatar == "/avatars/gf001.jpg"

    # GET /avatars/gf001.jpg works; /avatars/gf001.png is gone
    resp = await client.get("/avatars/gf001.jpg")
    assert resp.status == 200
    resp = await client.get("/avatars/gf001.png")
    assert resp.status == 404


async def test_avatar_delete_is_idempotent(avatar_api):
    """DELETE on a persona with no avatar returns 200 (no file to remove).

    The DELETE handler runs orphan cleanup unconditionally (T2 lesson #5),
    so deleting when no avatar exists is a no-op that still returns 200.
    """
    client, components, _tmp_path = avatar_api

    # No avatar uploaded yet
    assert components.persona_loader.get("gf001").avatar == ""

    # DELETE still succeeds (idempotent)
    resp = await client.delete("/api/persona/gf001/avatar")
    assert resp.status == 200
    data = await resp.json()
    assert data["ok"] is True

    # Second DELETE also succeeds
    resp = await client.delete("/api/persona/gf001/avatar")
    assert resp.status == 200


async def test_avatar_delete_orphan_cleanup_when_persona_not_found(avatar_api):
    """DELETE on unknown persona → 404, but orphan file cleanup still runs.

    T2 lesson #5: the DELETE handler does physical file cleanup FIRST
    (glob + unlink), THEN checks if persona exists. So even if the persona
    was deleted, a leftover avatar file is removed.
    """
    client, components, tmp_path = avatar_api
    avatar_dir = tmp_path / "avatars"
    avatar_dir.mkdir(parents=True, exist_ok=True)

    # Drop a phantom file for a persona that doesn't exist
    phantom_path = avatar_dir / "ghost_persona.png"
    phantom_path.write_bytes(_PNG_1X1)
    assert phantom_path.exists()

    # DELETE returns 404 (persona not found) but file is still cleaned up
    resp = await client.delete("/api/persona/ghost_persona/avatar")
    assert resp.status == 404
    data = await resp.json()
    assert data["error"] == "persona not found"

    # Orphan file removed despite 404
    assert not phantom_path.exists()


async def test_two_personas_have_independent_avatars(avatar_api):
    """Two personas → two independent avatar files + fields.

    Integration: avatar upload is per-persona_id (file path
    data/avatars/{persona_id}.{ext}). Uploading to gf001 does not
    affect gf002's avatar field or file.
    """
    client, components, tmp_path = avatar_api
    avatar_dir = tmp_path / "avatars"

    # Upload PNG for gf001
    resp = await client.post("/api/persona/gf001/avatar", data=_png_form())
    assert resp.status == 200
    assert (avatar_dir / "gf001.png").exists()

    # Upload JPEG for gf002
    resp = await client.post("/api/persona/gf002/avatar", data=_jpeg_form())
    assert resp.status == 200
    assert (avatar_dir / "gf002.jpg").exists()

    # Both files coexist
    assert (avatar_dir / "gf001.png").exists()
    assert (avatar_dir / "gf002.jpg").exists()

    # GET /api/persona shows independent avatar URLs
    resp = await client.get("/api/persona")
    personas = {p["id"]: p for p in await resp.json()}
    assert personas["gf001"]["avatar"] == "/avatars/gf001.png"
    assert personas["gf002"]["avatar"] == "/avatars/gf002.jpg"

    # Deleting gf001's avatar doesn't touch gf002's
    resp = await client.delete("/api/persona/gf001/avatar")
    assert resp.status == 200
    assert not (avatar_dir / "gf001.png").exists()
    assert (avatar_dir / "gf002.jpg").exists()

    # gf002's avatar field still set
    assert components.persona_loader.get("gf002").avatar == "/avatars/gf002.jpg"


# ════════════════════════════════════════════════════════════════
# T13 merged: PersonaLoader.delete removes avatar files (orphan cleanup)
# ════════════════════════════════════════════════════════════════


def test_persona_delete_removes_avatar_file_t13(tmp_path, monkeypatch):
    """T13: PersonaLoader.delete removes avatar files (orphan cleanup).

    The T12 plan specified: "Persona delete (PersonaLoader.delete) →
    avatar file removed (orphan cleanup, T13 feature — test may need to
    skip if T13 not merged yet, document)".

    T13 has now merged: PersonaLoader.delete (core/persona/loader.py:
    125-142) extends the original delete with `glob.glob(_AVATAR_DIR /
    "{persona_id}.*")` + unlink for each match. This test verifies the
    cleanup works end-to-end with a real PersonaLoader.

    IMPORTANT: T13's cleanup reads the module-level `_AVATAR_DIR`
    constant (DATA_DIR / "avatars"). The test monkeypatches it to
    tmp_path / "avatars" so the cleanup looks in the isolated test
    directory — without this patch, the test would be a false positive
    (file placed in tmp_path, cleanup looks in real data/avatars,
    file survives, test passes for the wrong reason).

    Initial version of this test (pre-T13) asserted the file SURVIVED
    delete and documented the T13 gap. T13's merge flipped the
    behavior — the test now asserts the file IS removed.
    """
    from core.persona import loader as loader_mod

    # Monkeypatch _AVATAR_DIR to tmp_path / "avatars" so the cleanup
    # code looks in the test's isolated directory, not the real
    # data/avatars.
    avatar_dir = tmp_path / "avatars"
    monkeypatch.setattr(loader_mod, "_AVATAR_DIR", avatar_dir)

    # Real PersonaLoader backed by tmp_path personas.json
    personas_file = tmp_path / "personas.json"
    loader = loader_mod.PersonaLoader(personas_file)
    loader.add(Persona(id="gf001", name="Test"))

    # Create avatar file for gf001
    avatar_dir.mkdir(parents=True, exist_ok=True)
    avatar_file = avatar_dir / "gf001.png"
    avatar_file.write_bytes(_PNG_1X1)
    assert avatar_file.exists()

    # Set avatar field on persona (simulating prior upload)
    loader.update("gf001", avatar="/avatars/gf001.png")

    # Delete the persona → T13 cleanup removes the avatar file
    deleted = loader.delete("gf001")
    assert deleted is True
    assert loader.get("gf001") is None
    assert not avatar_file.exists(), (
        "T13 PersonaLoader.delete should have removed the avatar file "
        "via glob + unlink orphan cleanup."
    )


def test_persona_delete_removes_all_avatar_extensions_t13(tmp_path, monkeypatch):
    """T13: delete() removes ALL avatar files matching {persona_id}.* (any ext).

    If a persona was uploaded as PNG then re-uploaded as JPG, only the
    JPG should exist (T2 upload handler cleans old ext). But if somehow
    multiple extensions exist (manual file copy, partial cleanup
    failure), delete() must remove ALL of them — not just one.
    """
    from core.persona import loader as loader_mod

    avatar_dir = tmp_path / "avatars"
    monkeypatch.setattr(loader_mod, "_AVATAR_DIR", avatar_dir)

    personas_file = tmp_path / "personas.json"
    loader = loader_mod.PersonaLoader(personas_file)
    loader.add(Persona(id="gf001", name="Test"))

    # Create avatar files with multiple extensions (simulating orphans)
    avatar_dir.mkdir(parents=True, exist_ok=True)
    png_file = avatar_dir / "gf001.png"
    jpg_file = avatar_dir / "gf001.jpg"
    webp_file = avatar_dir / "gf001.webp"
    for f in (png_file, jpg_file, webp_file):
        f.write_bytes(_PNG_1X1)  # content doesn't matter; just needs to exist
    assert png_file.exists() and jpg_file.exists() and webp_file.exists()

    # delete() should glob {persona_id}.* and remove ALL matches
    loader.delete("gf001")

    assert not png_file.exists()
    assert not jpg_file.exists()
    assert not webp_file.exists()


def test_persona_delete_does_not_remove_other_personas_avatars(
    tmp_path, monkeypatch,
):
    """T13: delete() only removes the deleted persona's avatars, not others.

    glob pattern is `{persona_id}.*` — must not match other persona IDs.
    Verifies that deleting gf001 doesn't touch gf002's avatar file.
    """
    from core.persona import loader as loader_mod

    avatar_dir = tmp_path / "avatars"
    monkeypatch.setattr(loader_mod, "_AVATAR_DIR", avatar_dir)

    personas_file = tmp_path / "personas.json"
    loader = loader_mod.PersonaLoader(personas_file)
    loader.add(Persona(id="gf001", name="One"))
    loader.add(Persona(id="gf002", name="Two"))

    avatar_dir.mkdir(parents=True, exist_ok=True)
    gf001_avatar = avatar_dir / "gf001.png"
    gf002_avatar = avatar_dir / "gf002.png"
    gf001_avatar.write_bytes(_PNG_1X1)
    gf002_avatar.write_bytes(_PNG_1X1)

    # Delete gf001 only
    loader.delete("gf001")

    # gf001's avatar removed, gf002's avatar untouched
    assert not gf001_avatar.exists()
    assert gf002_avatar.exists()

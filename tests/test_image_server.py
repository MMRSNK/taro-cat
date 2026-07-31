import urllib.error
import urllib.request

import config
import image_server


def _mkpng(tmp_path, name):
    # 1x1 PNG bytes
    data = bytes.fromhex(
        "89504e470d0a1a0a0000000d494844520000000100000001080600000"
        "01f15c4890000000d49444154789c6360000002000100ffff0300000600"
        "05023d0a0a0000000049454e44ae426082")
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_publish_file_stores_and_prunes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "_KEEP", 3)
    names = []
    for i in range(5):
        src = _mkpng(tmp_path, f"f{i}.png")
        names.append(image_server.publish_file(str(src)))
    remaining = sorted(p.name for p in (tmp_path / "public").glob("*.png"))
    assert names[-1] == "f4.png"
    assert len(remaining) == 3               # pruned to newest _KEEP
    assert "f4.png" in remaining and "f0.png" not in remaining


def test_server_serves_png_and_404(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server.settings, "IMAGE_SERVER_PORT", 8199)
    _mkpng(tmp_path, "x.png")
    image_server.publish_file(str(tmp_path / "x.png"))
    image_server.start_background()
    with urllib.request.urlopen("http://127.0.0.1:8199/x.png", timeout=5) as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "image/png"
    try:
        urllib.request.urlopen("http://127.0.0.1:8199/x.txt", timeout=5)
        assert False, "non-png should 404"
    except urllib.error.HTTPError as e:
        assert e.code == 404


def test_start_background_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(image_server.settings, "IMAGE_SERVER_PORT", 8198)
    monkeypatch.setattr(config, "PUBLIC_DIR", tmp_path / "public")
    monkeypatch.setattr(image_server, "PUBLIC_DIR", tmp_path / "public")
    a = image_server.start_background()
    b = image_server.start_background()
    assert a is b

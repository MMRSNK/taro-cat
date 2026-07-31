import pytest

import upload_image


def test_upload_builds_public_url(monkeypatch):
    monkeypatch.setattr(upload_image.settings, "PUBLIC_IMAGE_BASE",
                        "https://img.s3nko.com/")
    # upload() lazily imports image_server.publish_file — patch it there.
    import image_server
    monkeypatch.setattr(image_server, "publish_file", lambda p: "forecast_x.png")
    url = upload_image.upload("whatever.png")
    assert url == "https://img.s3nko.com/forecast_x.png"


def test_upload_requires_base(monkeypatch):
    monkeypatch.setattr(upload_image.settings, "PUBLIC_IMAGE_BASE", None)
    with pytest.raises(SystemExit):
        upload_image.upload("whatever.png")

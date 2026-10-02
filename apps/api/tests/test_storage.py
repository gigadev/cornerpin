from pathlib import Path

import pytest

from cornerpin.core.storage import LocalStorage, check_key


def test_round_trip_and_delete(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    storage.put("tenants/a/lots/b/photos/c.jpg", b"bytes", "image/jpeg")
    assert storage.get("tenants/a/lots/b/photos/c.jpg") == b"bytes"
    storage.delete("tenants/a/lots/b/photos/c.jpg")
    storage.delete("tenants/a/lots/b/photos/c.jpg")  # deleting twice is fine
    with pytest.raises(FileNotFoundError):
        storage.get("tenants/a/lots/b/photos/c.jpg")


@pytest.mark.parametrize(
    "key",
    ["../outside.txt", "tenants/../../etc/passwd", "/absolute", "a//b", "a/", "", "UPPER/case",
     "a\\b", "a/b c"],
)  # fmt: skip
def test_keys_cannot_escape_the_storage_root(tmp_path: Path, key: str) -> None:
    with pytest.raises(ValueError, match="invalid storage key"):
        check_key(key)
    with pytest.raises(ValueError, match="invalid storage key"):
        LocalStorage(tmp_path).put(key, b"x", "text/plain")

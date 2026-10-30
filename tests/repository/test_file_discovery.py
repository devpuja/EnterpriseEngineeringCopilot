import pytest

from app.repository.exceptions import RepositoryLimitExceededError
from app.repository.file_discovery import FileDiscovery, is_binary_file


def test_recursive_discovery_relative_paths_and_hash(tmp_path):
    package = tmp_path / "src"
    package.mkdir()
    source = package / "main.py"
    source.write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.js").write_text("ignored", encoding="utf-8")

    files = FileDiscovery().discover(tmp_path)
    assert len(files) == 1
    assert files[0].relative_path == "src/main.py"
    assert files[0].language == "Python"
    assert "Python" in files[0].technologies
    assert files[0].content_hash


def test_binary_and_sensitive_files(tmp_path):
    (tmp_path / "payload.bin").write_bytes(b"\x00\x01\x02\x03")
    (tmp_path / ".env").write_text("SECRET=value", encoding="utf-8")
    files = FileDiscovery().discover(tmp_path)
    assert files[0].relative_path == "payload.bin"
    assert files[0].is_binary
    assert len(files) == 1


def test_file_size_limit(tmp_path):
    source = tmp_path / "large.txt"
    source.write_bytes(b"x" * 20)
    discovery = FileDiscovery(maximum_file_size=10)
    try:
        discovery.discover(tmp_path)
        raise AssertionError("Expected repository limit exception")
    except RepositoryLimitExceededError:
        pass


def test_symlink_directory_is_not_followed(tmp_path):
    external = tmp_path.parent / "external-discovery"
    external.mkdir()
    (external / "secret.txt").write_text("outside", encoding="utf-8")
    try:
        (tmp_path / "linked").symlink_to(external, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable in this test environment: {exc}")

    files = FileDiscovery().discover(tmp_path)
    assert all("linked" not in item.relative_path for item in files)

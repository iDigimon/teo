"""Keep the two published distributions consistent without duplicating the plugin."""

from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
ALIAS_ROOT = ROOT / "packages" / "certbot-dns-tencent-edgeone"


def test_alias_tracks_core_release_and_python_support():
    core = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    alias = tomllib.loads((ALIAS_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert alias["name"] == "certbot-dns-tencent-edgeone"
    assert alias["version"] == core["version"]
    assert alias["requires-python"] == core["requires-python"]
    assert alias["dependencies"] == [f"certbot-dns-teo=={core['version']}"]
    assert not alias.get("entry-points")
    assert (ALIAS_ROOT / "LICENSE").read_bytes() == (ROOT / "LICENSE").read_bytes()

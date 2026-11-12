"""constraints.txt pins the installed `ytchat` command to the exact versions in uv.lock.

`uv tool install .` ignores uv.lock and takes the newest release of every dependency, so
the install instructions pass `-c constraints.txt`. If this test fails, uv.lock changed:
regenerate the file with the command at its top.
"""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
PROJECT = "video-summarisation-project"


def runtime_packages_in_lock() -> dict[str, str]:
    """name -> version for the project's runtime dependencies (not the dev group), transitively."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock["package"]}
    found: dict[str, str] = {}
    todo = [dep["name"] for dep in packages[PROJECT].get("dependencies", [])]
    while todo:
        name = todo.pop()
        if name not in found:
            found[name] = packages[name]["version"]
            todo += [dep["name"] for dep in packages[name].get("dependencies", [])]
    return found


def pinned_in_constraints() -> dict[str, str]:
    text = (ROOT / "constraints.txt").read_text(encoding="utf-8")
    return {name.lower().replace("_", "-"): version for name, version in re.findall(r"^([A-Za-z0-9._-]+)==([^\s;\\]+)", text, re.M)}


def test_constraints_match_the_lock_file():
    assert pinned_in_constraints() == runtime_packages_in_lock()


def test_docs_install_with_the_constraints():
    for doc in ("README.md", "startupGuide.md", "CLAUDE.md"):
        text = (ROOT / doc).read_text(encoding="utf-8")
        installs = re.findall(r"uv tool install\b[^\n`]*", text)
        assert installs, doc
        for command in installs:
            if "uv tool install ." in command or "--reinstall ." in command:
                assert "-c constraints.txt" in command, f"{doc}: {command}"
            assert "--upgrade" not in command or "--upgrade-package" in command, f"{doc}: {command}"

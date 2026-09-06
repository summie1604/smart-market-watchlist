"""Credential loading.

Keys are read from a gitignored file at the repository root and returned to the caller
that needs them. Nothing here logs, formats, or reports a value — a credential that
reaches a log or an error message is exposed, and the cheapest way to guarantee it never
does is to have no code that could print it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = ["load_credential"]

_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def _repo_root() -> Path:
    """Walk up until the marker file that identifies the repository root.

    ``tsconfig.base.json`` is the marker because it exists only at the root — every
    package has its own ``Makefile`` and several have a ``README.md`` — and because the
    frontend build cannot succeed without it, so it cannot quietly disappear.
    """
    for directory in [Path.cwd(), *Path(__file__).resolve().parents]:
        for candidate in [directory, *directory.parents]:
            if (candidate / "tsconfig.base.json").is_file():
                return candidate
    return Path.cwd()


def load_credential(name: str, filename: str = "GEMINI.ENV") -> str:
    """Return the named credential, or an empty string.

    The environment wins, so a deployment can supply the value without a file. Absence
    is an empty string rather than an exception: a missing credential is a coverage fact
    the pipeline reports, not a crash (D5).
    """
    from_env = os.environ.get(name, "")
    if from_env:
        return from_env

    path = _repo_root() / filename
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    for line in raw.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if match and match.group(1) == name:
            return match.group(2).strip().strip('"').strip("'")
    return ""

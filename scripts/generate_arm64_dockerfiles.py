#!/usr/bin/env python3
"""Emit dockerfiles_arm64/ from dockerfiles/ with arm64-oriented edits.

Edits applied
------------
1. First remote ``FROM`` (not ``FROM base_...``) gets ``--platform=linux/arm64``
   so pulls match the build host when building .sif / images on aarch64.
2. ``GOOS=linux GOARCH=amd64`` -> ``GOOS=linux GOARCH=arm64`` (Teleport builds).
3. ``deb [arch=amd64]`` for Google Linux packages -> ``deb [arch=arm64]``.
4. Open Library *base* Dockerfiles that install Google Chrome plus an amd64-only
   ChromeDriver zip: replace that whole block with Debian ``chromium`` +
   ``chromium-driver`` and symlinks so ``google-chrome-stable`` and
   ``/usr/local/bin/chromedriver`` keep working.

Regenerate::

    python scripts/generate_arm64_dockerfiles.py

Use with the harness::

    export SWEBENCH_DOCKERFILES_ROOT=dockerfiles_arm64

ECR images and other third-party bases must publish a linux/arm64 manifest or
the build will still fail; this script only adjusts Dockerfiles, not registry
content.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "dockerfiles"
DST = REPO_ROOT / "dockerfiles_arm64"

_COMBINED_CHROME_RE = re.compile(
    r"# Install Chrome for (?:integration tests|Selenium tests)\s*\r?\n"
    r".*?"
    r"RUN CHROMEDRIVER_VERSION=.*?&& rm(?: -rf)? /tmp/chromedriver[^\r\n]*\s*\r?\n",
    re.DOTALL,
)

_DEBIAN_BROWSER_ARM64 = (
    "# Browser stack for arm64 (Debian chromium + driver; avoids amd64 ChromeDriver zips)\n"
    "RUN apt-get update && apt-get install -y chromium chromium-driver xvfb \\\n"
    "    && rm -rf /var/lib/apt/lists/* \\\n"
    "    && ln -sf /usr/bin/chromium /usr/bin/google-chrome-stable \\\n"
    "    && ln -sf /usr/bin/chromium /usr/local/bin/google-chrome-stable \\\n"
    "    && ln -sf /usr/bin/chromedriver /usr/local/bin/chromedriver\n\n"
)


def _pin_first_remote_from(content: str) -> str:
    lines = content.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped.upper().startswith("FROM "):
            continue
        rest = stripped[5:].strip()
        if rest.upper().startswith("--PLATFORM"):
            break
        if rest.startswith("base_"):
            break
        indent = line[: len(line) - len(stripped)]
        lines[i] = f"{indent}FROM --platform=linux/arm64 {rest}\n"
        break
    return "".join(lines)


def _transform(content: str, rel_posix: str) -> str:
    out = _pin_first_remote_from(content)
    out = out.replace("GOOS=linux GOARCH=amd64", "GOOS=linux GOARCH=arm64")

    if (
        "base_dockerfile/" in rel_posix
        and "instance_internetarchive__openlibrary" in rel_posix
    ):
        m = _COMBINED_CHROME_RE.search(out)
        if m:
            out = out[: m.start()] + _DEBIAN_BROWSER_ARM64 + out[m.end() :]

    out = out.replace("deb [arch=amd64]", "deb [arch=arm64]")
    return out


def main() -> int:
    if not SRC.is_dir():
        print(f"Missing source tree: {SRC}", file=sys.stderr)
        return 1

    if DST.exists():
        shutil.rmtree(DST)

    n = 0
    for src_path in sorted(SRC.rglob("Dockerfile")):
        rel = src_path.relative_to(SRC)
        dst_path = DST / rel
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        text = src_path.read_text(encoding="utf-8")
        rel_posix = rel.as_posix()
        dst_path.write_text(_transform(text, rel_posix), encoding="utf-8")
        n += 1

    print(f"Wrote {n} Dockerfiles under {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

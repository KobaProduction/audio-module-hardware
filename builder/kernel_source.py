"""Verified kernel archive staging, independent from any OS distribution.

A SHA256-pinned archive of a *fixed* upstream commit avoids the very slow
per-blob checkout of GitHub's partial clone for the large A113X source tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path, PurePosixPath
import posixpath
import stat
import tarfile

STAMP = ".audio-module-kernel-source.json"


class KernelSourceError(ValueError):
    pass


def _tree_fingerprint(root: Path) -> dict:
    digest = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if rel == STAMP:
            continue
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            kind, value = "dir", ""
        elif stat.S_ISREG(info.st_mode):
            kind, value = "file", _hash_file(path)
        elif stat.S_ISLNK(info.st_mode):
            kind, value = "link", os.readlink(path)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(rel), value))
            if value.startswith("/") or resolved == ".." or resolved.startswith("../"):
                raise KernelSourceError("Kernel tree symlink escapes source root")
        else:
            raise KernelSourceError("Unexpected kernel source file type: " + rel)
        digest.update(json.dumps([rel, kind, stat.S_IMODE(info.st_mode), value],
                                 separators=(",", ":")).encode("utf-8") + b"\n")
        count += 1
    return {"sha256": digest.hexdigest(), "entries": count}


def _hash_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(4 * 1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify_archive_tree(src: Path, revision: str, archive_sha256: str) -> None:
    stamp = src / STAMP
    if not stamp.is_file() or stamp.is_symlink():
        raise KernelSourceError("Kernel archive tree has no verified source marker")
    record = json.loads(stamp.read_text(encoding="utf-8"))
    if (record.get("schema") != 1 or record.get("revision") != revision
            or record.get("archive_sha256") != archive_sha256
            or record.get("tree") != _tree_fingerprint(src)):
        raise KernelSourceError("Kernel archive source changed since extraction")


def extract_archive(archive: Path, src: Path, revision: str, archive_sha256: str,
                    repository: str) -> Path:
    """Extract only a verified, fixed-commit GitHub source archive.

    Archive SHA256 is already checked by the caller. Reject links outside the
    source root and special files before extracting anything. Never overwrite a
    working kernel tree. Leave an interrupted stage explicit, not silently reused.
    """
    if src.exists() or src.is_symlink():
        raise KernelSourceError("Kernel source directory already exists")
    stage = src.with_name(src.name + ".incomplete")
    if stage.exists() or stage.is_symlink():
        raise KernelSourceError("Incomplete kernel extraction requires inspection")
    prefix = repository.rsplit("/", 1)[-1] + "-" + revision
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf:
            name = member.name
            if name == prefix and member.isdir():
                continue
            if not name.startswith(prefix + "/"):
                raise KernelSourceError("Kernel archive has an unexpected path prefix")
            rel = name[len(prefix) + 1:]
            p = PurePosixPath(rel)
            if not rel or p.is_absolute() or any(x in (".", "..") for x in p.parts):
                raise KernelSourceError("Kernel archive contains an unsafe path")
            if not (member.isfile() or member.isdir() or member.issym()):
                raise KernelSourceError("Kernel archive contains a special or hardlink entry")
            if member.issym():
                link = member.linkname
                target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), link))
                if link.startswith("/") or target == ".." or target.startswith("../"):
                    raise KernelSourceError("Kernel archive contains an external symlink")
    stage.mkdir(parents=True)
    # All members have been checked; GNU tar strips exactly the archive prefix.
    # Neither U-Boot nor NAND is accessed in this host-only source operation.
    subprocess.run(["tar", "--no-same-owner", "--strip-components=1", "-xzf",
                    str(archive), "-C", str(stage)], check=True)
    if not (stage / "Makefile").is_file():
        raise KernelSourceError("Extracted kernel source has no Makefile")
    marker = {"schema": 1, "revision": revision, "archive_sha256": archive_sha256,
              "tree": _tree_fingerprint(stage)}
    (stage / STAMP).write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")
    stage.rename(src)
    return src

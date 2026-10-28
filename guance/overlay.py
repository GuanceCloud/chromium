#!/usr/bin/env python3
"""Overlay tracked fork changes on a pinned, dependency-complete source archive."""
import json
import os
from pathlib import Path
import subprocess
import sys


def overlay(repo, source, base, state):
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    paths = set(filter(None, git("diff", "--no-renames", "--name-only", "-z", base,
                                 "HEAD", "--", ".", ":(exclude)guance",
                                 ":(exclude).github").decode().split("\0")))
    # This archive fixes dependency/toolchain revisions. A DEPS roll needs a new
    # prepared archive or gclient sync, rather than an apparently successful copy.
    if any(Path(p).name == "DEPS" or p == "chrome/VERSION" for p in paths):
        raise ValueError("Dependency/version changes require updating the source preparation strategy")
    previous = set(json.loads(state.read_text())) if state.exists() else set()
    all_paths = paths | previous
    trees = {}
    for revision in (base, "HEAD"):
        entries = {}
        if all_paths:
            for raw in git("ls-tree", "-z", revision, "--", *sorted(all_paths)).split(b"\0"):
                if raw:
                    metadata, name = raw.split(b"\t", 1)
                    mode, kind, oid = metadata.decode().split()
                    if kind != "blob":
                        raise ValueError("Submodule/tree overlays are unsupported: " + name.decode())
                    entries[name.decode()] = (mode, oid)
        trees[revision] = entries
    # Journal the union first: a later invocation can restore even files written
    # by an interrupted run whose fork revision is no longer being built.
    state.write_text(json.dumps(sorted(all_paths)) + "\n")
    for relative in sorted(all_paths):
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe overlay path: " + relative)
        target = source / path
        if not target.parent.resolve().is_relative_to(source):
            raise ValueError("Overlay escapes source directory: " + relative)
        entry = trees["HEAD" if relative in paths else base].get(relative)
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.exists():
            raise ValueError("Refusing to replace a directory: " + relative)
        if entry:
            mode, oid = entry
            data = git("cat-file", "blob", oid)
            target.parent.mkdir(parents=True, exist_ok=True)
            if mode == "120000":
                os.symlink(os.fsdecode(data), target)
            elif mode in ("100644", "100755"):
                target.write_bytes(data)
                target.chmod(0o755 if mode == "100755" else 0o644)
            else:
                raise ValueError("Unsupported Git mode: " + mode)
    state.write_text(json.dumps(sorted(paths)) + "\n")
    print(json.dumps({"fork_revision": git("rev-parse", "HEAD").decode().strip(),
                      "overlaid_files": len(paths)}))


if __name__ == "__main__":
    overlay(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), sys.argv[3],
            Path(sys.argv[4]))

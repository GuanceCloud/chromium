#!/usr/bin/env python3
"""Verify a staged ARM64 artifact on native Linux and publish its smoke result."""
import json
import platform
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

from package import sha256


def main():
    if platform.system() != "Linux" or platform.machine() not in ("aarch64", "arm64"):
        raise RuntimeError("Native Linux ARM64 runner required")
    incoming, destination = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    expected, filename = (incoming / "SHA256SUMS").read_text().strip().split(None, 1)
    filename = filename.strip()
    if Path(filename).name != filename or sha256(incoming / filename) != expected:
        raise ValueError("Artifact checksum mismatch")
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="headless-verify-") as temp:
        root = Path(temp)
        with tarfile.open(incoming / filename, "r:gz") as archive:
            for item in archive.getmembers():
                path = Path(item.name)
                if path.is_absolute() or ".." in path.parts or not (item.isfile() or item.isdir()):
                    raise ValueError("Unsafe artifact member")
            archive.extractall(root)
        dirs = list(root.iterdir())
        if len(dirs) != 1 or not dirs[0].is_dir():
            raise ValueError("Unexpected artifact layout")
        stage = dirs[0]
        info = json.loads((stage / "build-info.json").read_text())
        with (stage / "headless_shell").open("rb") as binary:
            header = binary.read(20)
        if info["architecture"] != "arm64" or header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != 183 or sha256(stage / "headless_shell") != info["binary_sha256"]:
            raise ValueError("Unexpected binary or metadata")
        smoke = subprocess.check_output(["node", str(Path(__file__).with_name("smoke.cjs")),
                                         str(stage / "headless_shell_low_memory"), str(stage / "smoke.png")], text=True)
        report = json.loads(smoke)
        if not report.get("passed"):
            raise RuntimeError("Native ARM64 smoke test did not pass")
        info["smoke"] = report
        (stage / "smoke.json").write_text(smoke)
        metadata = json.dumps(info, indent=2) + "\n"
        (stage / "build-info.json").write_text(metadata)
        (destination / "build-info.json").write_text(metadata)
        output = destination / filename
        with tarfile.open(output, "w:gz") as archive:
            archive.add(stage, arcname=stage.name)
        (destination / "SHA256SUMS").write_text(sha256(output) + "  " + filename + "\n")


if __name__ == "__main__":
    main()

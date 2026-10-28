#!/usr/bin/env python3
"""Stage runtime dependencies, verify CDP screenshots and package the result."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    source, mode, destination = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]).resolve()
    arch = sys.argv[4] if len(sys.argv) > 4 else "amd64"
    if arch not in ("amd64", "arm64"):
        raise ValueError("Unknown architecture")
    scripts = Path(__file__).resolve().parent
    output = source / "out" / ("Guance-" + ("arm64-" if arch == "arm64" else "") + mode)
    version = ".".join(line.split("=")[1].strip() for line in (source / "chrome/VERSION").read_text().splitlines())
    repo = scripts.parent
    revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    destination.mkdir(parents=True, exist_ok=True)
    name = f"guance-headless-shell-{version}-linux-{arch}-{mode}-{revision[:12]}"
    with tempfile.TemporaryDirectory(prefix="headless-package-") as temporary:
        stage = Path(temporary) / name
        stage.mkdir()
        gn = source / "buildtools/linux64/gn"
        dependencies = subprocess.check_output([str(gn), "desc", str(output),
                          "//headless:headless_shell", "runtime_deps"], cwd=source, text=True)
        for relative in sorted(set(dependencies.splitlines())):
            path = Path(relative)
            # Inspector overlay JS is already embedded in browser resources.
            if path.parts[0] == "gen":
                continue
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Unexpected runtime path: " + relative)
            original = (output / path).resolve()
            if not original.is_relative_to(source):
                raise ValueError("Runtime dependency escapes source: " + relative)
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            with target.open("rb") as stream:
                elf = stream.read(4) == b"\x7fELF"
            if elf:
                subprocess.run([str(source / "third_party/llvm-build/Release+Asserts/bin/llvm-strip"),
                                "--strip-unneeded", str(target)], check=True)
        if (output / "hyphen-data").exists():
            shutil.copytree(output / "hyphen-data", stage / "hyphen-data", dirs_exist_ok=True)
        for original, target in [(source / "LICENSE", "LICENSE.chromium"),
                                 (output / "args.gn", "build-args.gn"),
                                 (output / "baseline.gn", "baseline.gn"),
                                 (output / "effective-args.gn", "effective-args.gn"),
                                 (scripts / "README.md", "README.guance.md"),
                                 (scripts / "launch-low-memory.sh", "headless_shell_low_memory")]:
            shutil.copy2(original, stage / target)
        (stage / "headless_shell_low_memory").chmod(0o755)
        subprocess.run([sys.executable, "tools/licenses/licenses.py", "credits", "--target-os=linux",
                        "--gn-out-dir=" + str(output), "--gn-target=//headless:headless_shell",
                        str(stage / "THIRD_PARTY_LICENSES.html")], cwd=source, check=True)
        with (stage / "headless_shell").open("rb") as binary:
            header = binary.read(20)
        if header[:6] != b"\x7fELF\x02\x01" or int.from_bytes(header[18:20], "little") != {"amd64": 62, "arm64": 183}[arch]:
            raise ValueError("Unexpected ELF architecture")
        report = {"passed": False, "status": "pending native verification"}
        if arch == "amd64":
            node = os.environ.get("NODE_BINARY") or str(source / "third_party/node/linux/node-linux-x64/bin/node")
            smoke = subprocess.check_output([node, str(scripts / "smoke.cjs"),
                           str(stage / "headless_shell_low_memory"), str(stage / "smoke.png")], text=True)
            report = json.loads(smoke)
            if not report.get("passed"):
                raise RuntimeError("Smoke test did not pass")
            (stage / "smoke.json").write_text(smoke)
        info = {"version": version, "profile": mode, "architecture": arch, "fork_revision": revision,
                "binary_sha256": sha256(stage / "headless_shell"),
                "screenshots": "CDP Page.captureScreenshot", "smoke": report,
                "source": "https://github.com/GuanceCloud/chromium/tree/" + revision}
        metadata = json.dumps(info, indent=2) + "\n"
        (stage / "build-info.json").write_text(metadata)
        (destination / "build-info.json").write_text(metadata)
        archive = destination / (name + ".tar.gz")
        with tarfile.open(archive, "w:gz") as stream:
            stream.add(stage, arcname=name)
        digest = sha256(archive)
        (destination / "SHA256SUMS").write_text(digest + "  " + archive.name + "\n")
        print(json.dumps({"archive": str(archive), "sha256": digest, "smoke_passed": report["passed"]}))


if __name__ == "__main__":
    main()

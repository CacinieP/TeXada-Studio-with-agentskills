#!/usr/bin/env python3
"""Provision pinned Monaco assets once; runtime requires no package registry."""

import argparse
import base64
import hashlib
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

VERSION = "0.52.2"
URL = f"https://registry.npmjs.org/monaco-editor/-/monaco-editor-{VERSION}.tgz"
INTEGRITY = "GEQWEZmfkOGLdd3XK8ryrfWz3AIP8YymVXiPHEdewrUq7mh0qrKrfHLNCXcbB6sTnMLnOZ3ztSiKcciFUkIJwQ=="
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use an already downloaded npm tarball")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "state" / "vendor-cache")
    args = parser.parse_args()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    archive = args.archive or args.cache_dir / f"monaco-editor-{VERSION}.tgz"
    if not archive.exists():
        if args.archive:
            parser.error("The supplied archive does not exist")
        incoming = archive.with_suffix(".download")
        subprocess.run(["curl", "--fail", "--location", "--silent", "--show-error",
                        "--max-time", "180", URL, "-o", str(incoming)], check=True)
        incoming.replace(archive)
    actual = base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode()
    if actual != INTEGRITY:
        raise SystemExit("Monaco tarball integrity mismatch; no assets were installed")

    target = ROOT / "webui" / "static" / "monaco" / VERSION
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="monaco-", dir=args.cache_dir) as temp:
        stage = Path(temp) / VERSION
        stage.mkdir()
        hashes = {}
        with tarfile.open(archive, "r:gz") as package:
            for member in package.getmembers():
                if not (member.name.startswith("package/min/vs/")
                        or member.name == "package/LICENSE"):
                    continue
                if member.isdir():
                    continue
                relative = PurePosixPath(member.name).relative_to("package")
                if not member.isfile() or ".." in relative.parts:
                    raise SystemExit("Unexpected Monaco archive entry")
                dest = stage.joinpath(*relative.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = package.extractfile(member).read()
                dest.write_bytes(data)
                hashes[str(relative)] = hashlib.sha256(data).hexdigest()
        for required in ("LICENSE", "min/vs/loader.js", "min/vs/editor/editor.main.js",
                         "min/vs/editor/editor.main.css", "min/vs/base/worker/workerMain.js"):
            if required not in hashes:
                raise SystemExit(f"Missing required Monaco asset: {required}")
        manifest = "".join(f"{digest}  {name}\n" for name, digest in sorted(hashes.items()))
        (stage / "SHA256SUMS").write_text(manifest)
        if target.exists():
            for name, digest in hashes.items():
                path = target / name
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                    raise SystemExit(f"Existing assets differ: {path}; inspect before replacing")
            print(f"Verified {len(hashes)} existing Monaco {VERSION} files")
            return
        shutil.move(str(stage), str(target))
    print(f"Installed {len(hashes)} verified Monaco {VERSION} files in {target}")


if __name__ == "__main__":
    main()

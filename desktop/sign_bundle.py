"""Sign every bundled Mach-O, including code under Resources, before its containers."""
from __future__ import annotations

import argparse
import plistlib
import subprocess
from pathlib import Path

# Thin and universal Mach-O headers, in either byte order.
MACHO_MAGICS = {
    b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca",
    b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
}
BUNDLE_SUFFIXES = {".app", ".framework", ".xpc", ".appex", ".bundle", ".plugin"}


def signing_targets(app: Path) -> tuple[list[Path], list[Path]]:
    """Avoid symlink aliases; seal nested bundles only after all their code."""
    binaries, bundles = [], []
    for path in app.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_file():
            with path.open("rb") as stream:
                if stream.read(4) in MACHO_MAGICS:
                    binaries.append(path)
        elif path.is_dir() and path.suffix in BUNDLE_SUFFIXES:
            if path.suffix == ".framework" or (path / "Contents" / "Info.plist").is_file():
                bundles.append(path)
    inside_out = lambda path: (-len(path.parts), str(path))
    return sorted(binaries, key=inside_out), sorted(bundles, key=inside_out)


def sign_bundle(app: Path, identity: str, entitlements: Path) -> None:
    app = app.resolve(strict=True)
    with (app / "Contents" / "Info.plist").open("rb") as stream:
        executable = plistlib.load(stream)["CFBundleExecutable"]
    # PyObjC callbacks need JIT in both the application launcher and py2app's
    # auxiliary Python interpreter. Libraries and TeX/Poppler tools do not.
    python_executables = {
        app / "Contents" / "MacOS" / executable,
        app / "Contents" / "MacOS" / "python",
    }
    binaries, bundles = signing_targets(app)
    if not binaries:
        raise ValueError(f"No Mach-O files found in {app}")

    def sign(path: Path, python: bool = False) -> None:
        command = ["codesign", "--force", "--options", "runtime", "--timestamp",
                   "--sign", identity]
        if python:
            command += ["--entitlements", str(entitlements)]
        subprocess.run([*command, str(path)], check=True)

    for binary in binaries:
        sign(binary, binary in python_executables)
    for bundle in bundles:
        sign(bundle)
    sign(app, python=True)
    for binary in binaries:
        subprocess.run(["codesign", "--verify", "--strict", str(binary)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)],
                   check=True)
    print(f"Signed and verified {len(binaries)} Mach-O files and {len(bundles) + 1} bundles")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--identity", required=True)
    parser.add_argument("--entitlements", type=Path,
                        default=Path(__file__).with_name("entitlements.plist"))
    args = parser.parse_args(argv)
    sign_bundle(args.app, args.identity, args.entitlements.resolve(strict=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Staple and validate an accepted notarization, retrying only EX_NOHOST (68)."""
import argparse
from pathlib import Path
import subprocess
import time


def _step(path, operation):
    for attempt in range(1, 4):
        result = subprocess.run(['xcrun', 'stapler', operation, str(path)], check=False)
        if result.returncode == 0:
            return 0
        if result.returncode != 68 or attempt == 3:
            return result.returncode
        print(f'stapler {operation}: transient network exit 68; retry {attempt + 1}/3 in 20 seconds', flush=True)
        time.sleep(20)
    return 68


def staple_and_validate(path):
    for operation in ('staple', 'validate'):
        code = _step(path, operation)
        if code:
            return code
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    args = parser.parse_args()
    return staple_and_validate(args.bundle)


if __name__ == '__main__':
    raise SystemExit(main())

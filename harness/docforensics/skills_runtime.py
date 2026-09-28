"""An explicit, allowlisted Skill loader for the fixed formula-repair host."""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re

DEFAULT_SKILL_ROOT = Path(__file__).resolve().parents[2] / "skills"
ALLOWED_SKILLS = frozenset({"doc-formula-verify"})
MAX_SKILL_BYTES = 64 * 1024


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def file_sha256(path):
    """A missing optional tool has a different identity from a present one."""
    try:
        return sha256_bytes(Path(path).read_bytes())
    except OSError:
        return None


@dataclass(frozen=True)
class LoadedSkill:
    name: str
    instructions: str
    sha256: str
    checker_sha256: str | None


def load_skill(name="doc-formula-verify", skill_root=None):
    """Validate and read exact UTF-8 instructions. Never execute Skill code.

    The intentionally limited frontmatter parser accepts scalar metadata, not
    general YAML. Neither the Skill nor its checker may resolve outside root.
    """
    if name not in ALLOWED_SKILLS:
        raise ValueError("skill_not_allowed")
    try:
        root = Path(skill_root or DEFAULT_SKILL_ROOT).resolve(strict=True)
        path = (root / name / "SKILL.md").resolve(strict=True)
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("skill_path_escape")
        with path.open("rb") as handle:
            raw = handle.read(MAX_SKILL_BYTES + 1)
    except OSError as exc:
        raise ValueError("skill_unavailable") from exc
    if len(raw) > MAX_SKILL_BYTES:
        raise ValueError("skill_too_large")
    try:
        instructions = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("skill_invalid_encoding") from exc
    lines = instructions.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("skill_missing_frontmatter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("skill_missing_frontmatter") from exc
    fields = {}
    for line in lines[1:closing]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):\s*(.+)", line)
        if not match or match[1] in fields:
            raise ValueError("skill_invalid_frontmatter")
        value = match[2].strip()
        if value.startswith(("'", '"')):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError("skill_invalid_frontmatter")
            value = value[1:-1]
        fields[match[1]] = value
    if fields.get("name") != name:
        raise ValueError("skill_name_mismatch")
    if not fields.get("description") or not "\n".join(lines[closing + 1:]).strip():
        raise ValueError("skill_empty_instructions")
    checker = (root / name / "scripts" / "verify.py").resolve()
    if not checker.is_relative_to(root):
        raise ValueError("skill_path_escape")
    return LoadedSkill(name, instructions, sha256_bytes(raw), file_sha256(checker))

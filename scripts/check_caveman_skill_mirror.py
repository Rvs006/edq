from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = REPO_ROOT / ".augment" / "skills"
MIRROR_ROOT = REPO_ROOT / ".kiro" / "skills"
SKILL_PREFIX = "caveman"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_skill_files(root: Path) -> dict[Path, str]:
    files: dict[Path, str] = {}

    for skill_dir in sorted(path for path in root.iterdir() if path.is_dir() and path.name.startswith(SKILL_PREFIX)):
        for file_path in sorted(path for path in skill_dir.rglob("*") if path.is_file()):
            files[file_path.relative_to(root)] = _hash_file(file_path)

    return files


def validate_caveman_skill_mirror(
    canonical_root: Path = CANONICAL_ROOT,
    mirror_root: Path = MIRROR_ROOT,
) -> list[str]:
    if not canonical_root.exists():
        return [f"Canonical skills root does not exist: {canonical_root}"]

    if not mirror_root.exists():
        return [f"Mirror skills root does not exist: {mirror_root}"]

    canonical_files = _collect_skill_files(canonical_root)
    mirror_files = _collect_skill_files(mirror_root)

    if not canonical_files:
        return [f"No canonical {SKILL_PREFIX} skills found under: {canonical_root}"]

    errors: list[str] = []

    missing_files = sorted(set(canonical_files) - set(mirror_files))
    extra_files = sorted(set(mirror_files) - set(canonical_files))
    changed_files = sorted(
        path
        for path in set(canonical_files) & set(mirror_files)
        if canonical_files[path] != mirror_files[path]
    )

    errors.extend(f"Missing mirrored file: {path.as_posix()}" for path in missing_files)
    errors.extend(f"Unexpected mirrored file: {path.as_posix()}" for path in extra_files)
    errors.extend(f"Content drift detected: {path.as_posix()}" for path in changed_files)

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that mirrored .kiro caveman skill files match .augment exactly."
    )
    parser.add_argument("--canonical-root", type=Path, default=CANONICAL_ROOT)
    parser.add_argument("--mirror-root", type=Path, default=MIRROR_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = validate_caveman_skill_mirror(
        canonical_root=args.canonical_root,
        mirror_root=args.mirror_root,
    )

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(
        f"Verified {SKILL_PREFIX} skill mirror: "
        f"{args.canonical_root.relative_to(REPO_ROOT)} == {args.mirror_root.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

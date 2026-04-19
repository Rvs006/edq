from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


def _load_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "scripts" / "check_caveman_skill_mirror.py"
    spec = importlib.util.spec_from_file_location("check_caveman_skill_mirror", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class ValidateCavemanSkillMirrorTests(unittest.TestCase):
    def test_accepts_matching_files(self):
        module = _load_module()

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            canonical_root = tmp_path / ".augment" / "skills"
            mirror_root = tmp_path / ".kiro" / "skills"

            _write_file(canonical_root / "caveman" / "SKILL.md", "canonical")
            _write_file(canonical_root / "caveman-compress" / "scripts" / "cli.py", "print('ok')\n")
            _write_file(canonical_root / "not-caveman" / "SKILL.md", "ignored")

            _write_file(mirror_root / "caveman" / "SKILL.md", "canonical")
            _write_file(mirror_root / "caveman-compress" / "scripts" / "cli.py", "print('ok')\n")
            _write_file(mirror_root / "not-caveman" / "SKILL.md", "ignored but not compared")

            self.assertEqual(module.validate_caveman_skill_mirror(canonical_root, mirror_root), [])

    def test_reports_drift(self):
        module = _load_module()

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            canonical_root = tmp_path / ".augment" / "skills"
            mirror_root = tmp_path / ".kiro" / "skills"

            _write_file(canonical_root / "caveman" / "SKILL.md", "canonical")
            _write_file(canonical_root / "caveman-help" / "SKILL.md", "help text")
            _write_file(canonical_root / "caveman-compress" / "scripts" / "cli.py", "print('source')\n")

            _write_file(mirror_root / "caveman" / "SKILL.md", "drifted")
            _write_file(mirror_root / "caveman-compress" / "scripts" / "cli.py", "print('source')\n")
            _write_file(mirror_root / "caveman-compress" / "scripts" / "extra.py", "extra\n")

            errors = module.validate_caveman_skill_mirror(canonical_root, mirror_root)

            self.assertEqual(
                errors,
                [
                    "Missing mirrored file: caveman-help/SKILL.md",
                    "Unexpected mirrored file: caveman-compress/scripts/extra.py",
                    "Content drift detected: caveman/SKILL.md",
                ],
            )


if __name__ == "__main__":
    unittest.main()

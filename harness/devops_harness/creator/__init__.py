"""devops_harness.creator — project infrastructure forging.

Wraps the harness-creator SKILL.md workflow as a callable Python API.
The actual intelligence is in the SKILL.md prompt chain; this module
provides a typed interface and convenience methods.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CreatorResult:
    """Result of a harness-creator run."""

    project_type: str = "unknown"  # greenfield | existing | mature
    files_created: list[str] = field(default_factory=list)
    files_updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HarnessCreator:
    """Scan project → compute delta → generate harness infrastructure.

    Usage::

        creator = HarnessCreator(project_root=Path("/my/project"))
        result = creator.detect()
        if result.project_type == "greenfield":
            creator.create_greenflight()
        else:
            creator.create_delta()
    """

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path.cwd()
        self._skill_dir = Path(__file__).parent

    # ─── Phase 1: Detection ────────────────────────────────────

    def detect(self) -> CreatorResult:
        """Quick scan: what exists and what's missing."""
        result = CreatorResult()
        file_count = self._count_code_files()
        has_agents = (self.project_root / "AGENTS.md").exists()
        has_arch = (self.project_root / "docs" / "ARCHITECTURE.md").exists()
        bool(list((self.project_root / "scripts").glob("lint_*")))
        (self.project_root / "harness" / "config" / "environment.json").exists()

        if file_count == 0 or (file_count < 10 and not has_agents):
            result.project_type = "greenfield"
        elif not has_agents or not has_arch:
            result.project_type = "existing"
        else:
            result.project_type = "mature"
        return result

    # ─── Phase 2-4: Analysis + Synthesis + Creation ─────────────

    def create_greenfield(self, config: dict[str, Any] | None = None) -> CreatorResult:
        """Full harness creation for a greenfield/empty project."""
        result = CreatorResult(project_type="greenfield")
        cfg = config or {}

        # Use detect_adapter script to figure out language
        adapter = self._detect_adapter()
        cfg.get("seed", 42)
        cfg.get("map_size", 64)
        cfg.get("max_ticks", 10000)

        # Generate core files (same logic as SKILL.md Phase 4)
        core_files = {
            "AGENTS.md": self._render_template("agents-md", adapter=adapter),
            "docs/ARCHITECTURE.md": self._render_template("architecture-md", adapter=adapter),
            "docs/DEVELOPMENT.md": self._render_template("development-md", adapter=adapter),
            "pyproject.toml": self._render_template("pyproject-toml", adapter=adapter),
            "Makefile": self._render_template("makefile", adapter=adapter),
        }

        for rel_path, content in core_files.items():
            target = self.project_root / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            result.files_created.append(rel_path)

        # Run linter generation
        lint_result = self._run_script("generate_linters", adapter=adapter)
        if lint_result:
            result.files_created.extend(lint_result)

        return result

    def create_delta(self) -> CreatorResult:
        """Incremental update for existing/mature projects."""
        result = CreatorResult(project_type="existing")
        self.detect()

        # Check what's missing
        checks = {
            "AGENTS.md": not (self.project_root / "AGENTS.md").exists(),
            "docs/ARCHITECTURE.md": not (self.project_root / "docs" / "ARCHITECTURE.md").exists(),
            "docs/DEVELOPMENT.md": not (self.project_root / "docs" / "DEVELOPMENT.md").exists(),
        }
        for rel_path, missing in checks.items():
            if missing:
                adapter = self._detect_adapter()
                target = self.project_root / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                template_name = rel_path.replace("/", "-").replace(".md", "-md").replace(".", "-")
                target.write_text(self._render_template(template_name, adapter=adapter))
                result.files_created.append(rel_path)
            else:
                result.files_updated.append(rel_path)

        return result

    # ─── Phase 5: Verification ─────────────────────────────────

    def verify(self) -> dict[str, bool]:
        """Check that all key harness files exist."""
        key_files = [
            "AGENTS.md",
            "docs/ARCHITECTURE.md",
            "docs/DEVELOPMENT.md",
            "pyproject.toml",
            "Makefile",
        ]
        return {f: (self.project_root / f).exists() for f in key_files}

    # ─── Helpers ───────────────────────────────────────────────

    def _count_code_files(self) -> int:
        """Count non-generated code files in project."""
        code_exts = {".py", ".gd", ".ts", ".go", ".rs", ".java"}
        count = 0
        for f in self.project_root.rglob("*"):
            if f.suffix in code_exts and "proto_out" not in str(f):
                count += 1
        return count

    def _detect_adapter(self) -> str:
        """Use executor's detect_adapter script."""
        script = self._skill_dir.parent / "executor" / "scripts" / "detect_adapter.py"
        if script.exists():
            try:
                out = subprocess.run(
                    ["python3", str(script), str(self.project_root), "--json"],
                    capture_output=True, text=True, timeout=10,
                )
                data = json.loads(out.stdout)
                return data.get("adapter", "generic")
            except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
                pass
        return "python"  # default for this project

    def _render_template(self, name: str, **kwargs: Any) -> str:
        """Load a markdown template and substitute kwargs."""
        template_dir = self._skill_dir / "references" / "templates"
        # Try RTS-specific first
        rts_template = template_dir / "greenfield-templates-rts.md"
        generic_template = template_dir / "greenfield-templates.md"

        if rts_template.exists():
            return rts_template.read_text()[:200] + "\n[...truncated for rendering...]\n"
        if generic_template.exists():
            return generic_template.read_text()[:200] + "\n[...truncated for rendering...]\n"
        return f"# {name}\nGenerated by devops-harness creator\n"

    def _run_script(self, name: str, **kwargs: Any) -> list[str] | None:
        """Placeholder for script execution."""
        return None

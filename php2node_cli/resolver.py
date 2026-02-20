from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

from .utils import (
    normalize_controller_filename,
    find_php_controllers_root,
    read_text,
    FileProbeResult,
)


@dataclass
class ResolvedEndpoint:
    controller_file: Optional[Path]
    app_resolved: Optional[str]  # api|portal|None
    probe: FileProbeResult


def probe_controller_file(
    repo_root: Path,
    controller: str,
    version: str,
    app_choice: str = "auto",
) -> Tuple[FileProbeResult, Optional[str]]:
    controller_file = normalize_controller_filename(controller)

    def candidates_for_app(app_name: str) -> List[Path]:
        app_root = repo_root / app_name
        base = find_php_controllers_root(app_root)
        return [
            base / version / controller_file,
            base / controller_file,
        ]

    tried: List[str] = []
    apps = ["api", "portal"] if app_choice == "auto" else [app_choice]

    # 1) Direct candidates
    for app in apps:
        for c in candidates_for_app(app):
            tried.append(str(c))
            if c.exists():
                return FileProbeResult(True, c, tried), app

    # 2) Filename search under controllers
    for app in apps:
        base = find_php_controllers_root(repo_root / app)
        tried.append(f"{base}/**/{controller_file}")
        if base.exists():
            hits = [p for p in base.rglob(controller_file)]
            if hits:
                return FileProbeResult(True, hits[0], tried), app

    # 3) Class-name grep fallback
    class_pat = re.compile(rf"\bclass\s+{re.escape(controller)}\b", re.IGNORECASE)
    for app in apps:
        base = find_php_controllers_root(repo_root / app)
        tried.append(f"{base}/**/*.php (grep class {controller})")
        if base.exists():
            for p in base.rglob("*.php"):
                try:
                    txt = read_text(p)
                except Exception:
                    continue
                if class_pat.search(txt):
                    return FileProbeResult(True, p, tried), app

    return FileProbeResult(False, None, tried), None


def resolve_controller(repo_root: Path, controller: str, version: str, app_choice: str = "auto") -> ResolvedEndpoint:
    probe, app_resolved = probe_controller_file(
        repo_root=repo_root,
        controller=controller,
        version=version,
        app_choice=app_choice,
    )
    return ResolvedEndpoint(
        controller_file=probe.path,
        app_resolved=app_resolved,
        probe=probe,
    )

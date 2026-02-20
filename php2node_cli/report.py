from __future__ import annotations

from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from .utils import write_text


def build_report_md(
    endpoint_original: str,
    inventory_row: Dict[str, Any],
    controller_file: Optional[Path],
    app_resolved: Optional[str],
    method_name: str,
    method_lines: Optional[Tuple[int, int]],
    dependencies: Dict[str, Any],
    risks: List[str],
) -> str:
    ctrl = str(controller_file) if controller_file else "NOT FOUND"
    app = app_resolved or "N/A"

    lines: List[str] = []
    lines.append("# Endpoint Migration Report")
    lines.append("")
    lines.append("## Input")
    lines.append(f"- Endpoint: `{endpoint_original}`")
    lines.append("")
    lines.append("## Inventory Match")
    lines.append(f"- Version: `{inventory_row.get('Version')}`")
    lines.append(f"- Controller: `{inventory_row.get('Controller')}`")
    lines.append(f"- HttpMethod: `{inventory_row.get('HttpMethod')}`")
    lines.append(f"- Method: `{inventory_row.get('Method')}`")
    lines.append(f"- MethodBase: `{inventory_row.get('MethodBase')}`")
    lines.append(f"- EndpointPath: `{inventory_row.get('EndpointPath')}`")
    lines.append(f"- EndpointPath with version: `{inventory_row.get('EndpointPath with version')}`")
    lines.append("")
    lines.append("## PHP Resolution")
    lines.append(f"- App: `{app}`")
    lines.append(f"- Controller file: `{ctrl}`")
    lines.append(f"- Method extracted: `{method_name}`")
    if method_lines:
        lines.append(f"- Method lines: `{method_lines[0]}..{method_lines[1]}`")
    lines.append("")
    lines.append("## Heuristic Dependencies Detected")
    lines.append(f"- Models: `{dependencies.get('models', [])}`")
    lines.append(f"- Helpers: `{dependencies.get('helpers', [])}`")
    lines.append(f"- Libraries: `{dependencies.get('libraries', [])}`")
    lines.append(f"- Uses $this->get(): `{dependencies.get('inputs_get')}`")
    lines.append(f"- Uses $this->post(): `{dependencies.get('inputs_post')}`")
    lines.append(f"- Uses $this->put(): `{dependencies.get('inputs_put')}`")
    lines.append(f"- Uses $this->delete(): `{dependencies.get('inputs_delete')}`")
    lines.append("")
    lines.append("## Risks / Pending Work")
    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("- None detected by heuristics. Manual review still required.")
    lines.append("")
    return "\n".join(lines)


def build_unresolved_md(title: str, details: List[str]) -> str:
    lines: List[str] = [f"# {title}", ""]
    for d in details:
        lines.append(f"- {d}")
    lines.append("")
    return "\n".join(lines)


def write_report(path: Path, content: str) -> None:
    write_text(path, content)

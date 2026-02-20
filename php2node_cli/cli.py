from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path
import os

from .inventory import Inventory
from .resolver import resolve_controller
from .extractor import extract_method_block, detect_dependencies, analyze_php_method
from .scaffold_node import generate_scaffold
from .report import build_report_md, build_unresolved_md, write_report
from .utils import (
    norm_http,
    norm_endpoint_path,
    norm_version,
    endpoint_key,
    ensure_dir,
    write_text,
    safe_slug,
)

LOG = logging.getLogger("php2node")


def setup_logging(verbosity: int) -> None:
    level = logging.INFO
    if verbosity >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(asctime)s | %(levelname)s | %(message)s")


def _load_dotenv_if_present() -> None:
    """
    Loads .env if python-dotenv is installed and a .env exists in CWD.
    We keep it optional so the tool still works without dotenv.
    """
    env_path = Path(".env")
    if not env_path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv(dotenv_path=str(env_path), override=False)
    except Exception as e:
        # Do not hard-fail: env is just convenience
        LOG.debug("dotenv not loaded: %s", e)


def _env(name: str) -> str | None:
    v = os.getenv(name)
    if v is None:
        return None
    v = v.strip()
    return v if v else None


def parse_args() -> argparse.Namespace:
    _load_dotenv_if_present()

    p = argparse.ArgumentParser(
        prog="php2node",
        description="Resolve CodeIgniter endpoint to PHP method and generate Node.js (Express+TS) scaffold.",
    )

    # defaults from .env
    default_repo = _env("PHP2NODE_REPO_ROOT")
    default_inv = _env("PHP2NODE_INVENTORY_XLSX")
    default_sheet = _env("PHP2NODE_SHEET") or "EndPoints"
    default_out = _env("PHP2NODE_OUT") or "./out"
    default_app = _env("PHP2NODE_APP") or "auto"

    p.add_argument("--repo-root", required=False, default=default_repo,
                   help="Local path to repo root. Also via PHP2NODE_REPO_ROOT in .env")
    p.add_argument("--inventory-xlsx", required=False, default=default_inv,
                   help="Path to inventory Excel. Also via PHP2NODE_INVENTORY_XLSX in .env")

    p.add_argument("--sheet", required=False, default=default_sheet,
                   help='Excel sheet name (default EndPoints). Also via PHP2NODE_SHEET in .env')

    p.add_argument("--out", required=False, default=default_out,
                   help="Output folder (default ./out). Also via PHP2NODE_OUT in .env")

    p.add_argument("--app", required=False, default=default_app, choices=["api", "portal", "auto"],
                   help="Search scope. Also via PHP2NODE_APP in .env")

    p.add_argument("--http-method", required=True, help="GET|POST|PUT|DELETE")
    p.add_argument("--endpoint-path", required=True, help='Example: "bank_account/dacustomer_bank" (no leading slash)')
    p.add_argument("--version", required=False, help="v1|v2 (optional). If omitted, inferred from inventory.")
    p.add_argument("--clean-out", action="store_true", help="Delete output folder before writing new results.")
    p.add_argument("-v", "--verbose", action="count", default=0, help="Increase log verbosity (-v, -vv)")

    return p.parse_args()


def _require_arg(value: str | None, flag: str, env_name: str) -> str:
    if value and value.strip():
        return value.strip()
    raise SystemExit(f"Missing {flag} (or {env_name} in .env)")


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    repo_root_str = _require_arg(args.repo_root, "--repo-root", "PHP2NODE_REPO_ROOT")
    inv_path_str = _require_arg(args.inventory_xlsx, "--inventory-xlsx", "PHP2NODE_INVENTORY_XLSX")

    repo_root = Path(repo_root_str).expanduser().resolve()
    inv_path = Path(inv_path_str).expanduser().resolve()
    out_root = Path(args.out).expanduser().resolve()

    if args.clean_out and out_root.exists():
        LOG.info("Cleaning output folder: %s", out_root)
        shutil.rmtree(out_root)

    ensure_dir(out_root)

    http_method = norm_http(args.http_method)
    endpoint_path = norm_endpoint_path(args.endpoint_path)
    version = norm_version(args.version) if args.version else None
    app_choice = args.app

    LOG.info("Stage 1: Load inventory")
    inv = Inventory.load(inv_path, sheet_name=args.sheet)

    if not version:
        LOG.info("Stage 1.1: Infer version (not provided)")
        versions = inv.infer_version(http_method=http_method, endpoint_path=endpoint_path)

        if len(versions) == 0:
            _, suggestions = inv.match(http_method=http_method, endpoint_path=endpoint_path, version=None)
            details = [
                f"Endpoint not found in inventory for {http_method} {endpoint_path}",
                f"Inventory file: {inv_path}",
                f"Sheet: {args.sheet}",
            ]
            if suggestions:
                details.append("Suggestions (partial matches):")
                for s in suggestions[:15]:
                    details.append(
                        f"  - {s.http_method} {s.version} {s.endpoint_path} | Controller={s.controller} Method={s.method}"
                    )
            unresolved_dir = out_root / "unresolved" / "unknown"
            ensure_dir(unresolved_dir)
            write_report(unresolved_dir / "unresolved.md", build_unresolved_md("Unresolved Endpoint", details))
            LOG.error("Unresolved: endpoint not found in inventory")
            return 2

        if len(versions) > 1:
            details = [
                f"Ambiguous version for {http_method} {endpoint_path}. Versions found: {versions}",
                "Re-run with --version v1 or --version v2.",
            ]
            unresolved_dir = out_root / "unresolved" / "ambiguous"
            ensure_dir(unresolved_dir)
            write_report(unresolved_dir / "unresolved.md", build_unresolved_md("Ambiguous Version", details))
            LOG.error("Unresolved: ambiguous version in inventory")
            return 2

        version = versions[0]
        LOG.info("Inferred version: %s", version)

    LOG.info("Stage 2: Match endpoint in inventory")
    exact, suggestions = inv.match(http_method=http_method, endpoint_path=endpoint_path, version=version)

    if len(exact) == 0:
        details = [
            f"No exact match in inventory for {http_method} {version} {endpoint_path}",
            f"Inventory file: {inv_path}",
            f"Sheet: {args.sheet}",
        ]
        if suggestions:
            details.append("Suggestions (partial matches):")
            for s in suggestions[:15]:
                details.append(
                    f"  - {s.http_method} {s.version} {s.endpoint_path} | Controller={s.controller} Method={s.method}"
                )
        unresolved_dir = out_root / "unresolved" / version
        ensure_dir(unresolved_dir)
        write_report(unresolved_dir / "unresolved.md", build_unresolved_md("Unresolved Endpoint", details))
        LOG.error("Unresolved: no exact inventory match")
        return 2

    if len(exact) > 1:
        details = [
            f"Multiple exact inventory matches for {http_method} {version} {endpoint_path}.",
            "Candidates:",
        ]
        for r in exact:
            details.append(f"  - Controller={r.controller} Method={r.method} MethodBase={r.method_base}")
        unresolved_dir = out_root / "unresolved" / version
        ensure_dir(unresolved_dir)
        write_report(unresolved_dir / "unresolved.md", build_unresolved_md("Ambiguous Inventory Match", details))
        LOG.error("Unresolved: multiple inventory matches")
        return 2

    row = exact[0]
    method_name = row.method

    LOG.info("Stage 3: Resolve controller file in repo")
    resolved = resolve_controller(repo_root=repo_root, controller=row.controller, version=row.version, app_choice=app_choice)
    if not resolved.controller_file:
        details = [
            "Inventory match found, but controller file could not be located.",
            f"Controller: {row.controller}",
            f"Version: {row.version}",
            f"Repo root: {repo_root}",
            f"App choice: {app_choice}",
            "Paths tried:",
        ]
        details += [f"  - {p}" for p in resolved.probe.tried[:30]]
        if len(resolved.probe.tried) > 30:
            details.append("  - (more paths omitted)")
        unresolved_dir = out_root / "unresolved" / row.version
        ensure_dir(unresolved_dir)
        write_report(unresolved_dir / "unresolved.md", build_unresolved_md("Controller Not Found", details))
        LOG.error("Unresolved: controller file not found")
        return 2

    LOG.info("Stage 4: Extract PHP method block")
    ext = extract_method_block(resolved.controller_file, method_name)
    if not ext.found or not ext.extracted:
        details = [
            "Controller file found, but method could not be extracted.",
            f"Controller file: {resolved.controller_file}",
            f"Method expected: {method_name}",
            "Notes:",
        ] + [f"  - {n}" for n in ext.notes]
        unresolved_dir = out_root / "unresolved" / row.version
        ensure_dir(unresolved_dir)
        write_report(unresolved_dir / "unresolved.md", build_unresolved_md("Method Not Found", details))
        LOG.error("Unresolved: method not extracted")
        return 2

    deps = detect_dependencies(ext.extracted)

    LOG.info("Stage 5: Write output structure")
    ekey = endpoint_key(row.version, http_method, endpoint_path)
    base_dir = out_root / "resolved" / row.version / ekey
    php_dir = base_dir / "php"
    node_dir = base_dir / "node"
    ensure_dir(php_dir)
    ensure_dir(node_dir)

    write_text(php_dir / "controller_path.txt", str(resolved.controller_file))
    write_text(php_dir / "method.php", ext.extracted)

    # analysis.json
    import json
    analysis = analyze_php_method(ext.extracted)
    write_text(php_dir / "analysis.json", json.dumps(analysis, indent=2, ensure_ascii=False))

    # Route path
    if row.endpoint_path_with_version:
        route_path = "/" + row.endpoint_path_with_version.lstrip("/")
    else:
        route_path = "/" + f"{row.version}/{row.endpoint_path}".lstrip("/")

    name_base = safe_slug(f"{row.controller}_{row.method_base}")

    LOG.info("Stage 6: Generate Node scaffold (Express + TS)")
    generate_scaffold(
        out_node_dir=node_dir,
        http_method=http_method,
        route_path=route_path,
        name_base=name_base,
        handler_name=row.method_base,
    )

    LOG.info("Stage 7: Generate report.md + changes.md")
    risks = []
    if deps.get("models"):
        risks.append("Uses CodeIgniter models. You must port model calls to Node (DB layer not defined in scaffold).")
    if deps.get("helpers"):
        risks.append("Uses CodeIgniter helpers. Identify helper behavior and replace with Node utilities.")
    if deps.get("libraries"):
        risks.append("Uses CodeIgniter libraries. Confirm equivalents in Node or re-implement.")

    # changes.md (A+B)
    changes_lines = [
        "# Changes: PHP -> Node",
        "",
        "## Endpoint",
        f"- {http_method} {endpoint_path}",
        "",
        "## Inputs mapping",
        f"- PHP $this->get(): {analysis.get('inputs', {}).get('get', [])} -> Node req.query",
        f"- PHP $this->post(): {analysis.get('inputs', {}).get('post', [])} -> Node req.body",
        f"- PHP $this->put(): {analysis.get('inputs', {}).get('put', [])} -> Node req.body",
        f"- PHP $this->delete(): {analysis.get('inputs', {}).get('delete', [])} -> Node req.query/params",
        "",
        "## Dependencies",
        f"- Models loaded: {analysis.get('models_loaded', [])}",
        f"- Model calls: {analysis.get('model_calls', [])}",
        "",
        "## Control flow",
        f"- Switch vars: {analysis.get('control_flow', {}).get('switch_vars', [])}",
        f"- Cases: {analysis.get('control_flow', {}).get('cases', [])}",
        "",
        "## Responses",
        f"- REST codes: {analysis.get('responses', {}).get('rest_codes', [])}",
        f"- Messages: {analysis.get('responses', {}).get('messages', [])}",
        "",
        "## TODO for migration",
        "- Implement service methods equivalent to CI models.",
        "- Align status codes and response schema.",
        "- Add auth/permissions middleware if required.",
        "",
    ]
    write_report(base_dir / "changes.md", "\n".join(changes_lines))

    report_md = build_report_md(
        endpoint_original=f"{http_method} {endpoint_path}",
        inventory_row=row.raw,
        controller_file=resolved.controller_file,
        app_resolved=resolved.app_resolved,
        method_name=method_name,
        method_lines=(ext.start_line, ext.end_line) if ext.start_line and ext.end_line else None,
        dependencies=deps,
        risks=risks,
    )
    write_report(base_dir / "report.md", report_md)

    LOG.info("Done. Output: %s", base_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

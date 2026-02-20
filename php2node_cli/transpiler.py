from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .utils import read_text, write_text


@dataclass
class TranspileResult:
    controller_ts: str
    service_ts: str
    types_ts: str
    semantic_md: str


def _extract_switch_cases(method_php: str) -> Tuple[str | None, List[str]]:
    """
    Very small heuristic:
      switch ($status) { case '1': ... getlist_customer_bank('COMPLETED'); break; ... }
    Returns (switch_var, cases)
    """
    m = re.search(r"switch\s*\(\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*{", method_php)
    switch_var = m.group(1) if m else None

    cases = re.findall(r"case\s+['\"]?([^'\"]+)['\"]?\s*:", method_php)
    cases = [c.strip() for c in cases if c.strip()]
    return switch_var, cases


def _extract_model_call_map(method_php: str) -> List[Dict[str, Any]]:
    """
    Extracts patterns like:
      $result = $this->bankaccount_model->getlist_customer_bank('COMPLETED');
    Returns list of dicts:
      {model: bankaccount_model, fn: getlist_customer_bank, args: ["'COMPLETED'"], assigns_to: "result"}
    """
    out: List[Dict[str, Any]] = []
    # capture "$var = $this->model->fn(args);"
    pat = re.compile(
        r"\$([A-Za-z_][A-Za-z0-9_]*)\s*=\s*\$this->([A-Za-z_][A-Za-z0-9_]*)->([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;",
        re.DOTALL,
    )
    for m in pat.finditer(method_php):
        assigns = m.group(1)
        model = m.group(2)
        fn = m.group(3)
        args_raw = m.group(4).strip()
        out.append(
            {
                "assigns_to": assigns,
                "model": model,
                "fn": fn,
                "args_raw": args_raw,
            }
        )
    return out


def transpile_endpoint(
    *,
    name_base: str,
    route_path: str,
    http_method: str,
    php_method_path: Path,
    analysis_json_path: Path,
) -> TranspileResult:
    php_method = read_text(php_method_path)
    analysis = json.loads(read_text(analysis_json_path))

    inputs = analysis.get("inputs", {})
    models_loaded = analysis.get("models_loaded", [])
    model_calls = analysis.get("model_calls", [])
    rest_codes = analysis.get("responses", {}).get("rest_codes", [])
    messages = analysis.get("responses", {}).get("messages", [])
    self_consts = analysis.get("constants", {}).get("self", [])

    switch_var, switch_cases = _extract_switch_cases(php_method)
    model_assignments = _extract_model_call_map(php_method)

    # Types
    input_keys = inputs.get("get", []) if http_method == "GET" else inputs.get("post", [])
    input_iface = "\n".join([f"  {k}?: string;" for k in input_keys]) or "  // TODO: define input fields"
    types_ts = f"""export interface {to_pascal(name_base)}Input {{
{input_iface}
}}

export interface {to_pascal(name_base)}Output {{
  // TODO: define output shape based on PHP response payload
  data?: unknown;
  status?: boolean;
  message?: string;
  response_code?: number;
}}
"""

    # Service
    service_lines: List[str] = []
    service_lines.append(f"import type {{ {to_pascal(name_base)}Input, {to_pascal(name_base)}Output }} from \"../types/{name_base}.types\";")
    service_lines.append("")
    service_lines.append(f"export class {to_pascal(name_base)}Service {{")
    service_lines.append(f"  public async execute(input: {to_pascal(name_base)}Input): Promise<{to_pascal(name_base)}Output> {{")
    service_lines.append("    // TODO: port business logic from PHP")
    if models_loaded:
        service_lines.append(f"    // PHP loads models: {models_loaded}")
    if model_calls:
        service_lines.append(f"    // PHP calls (heuristic): {model_calls}")
    service_lines.append("")
    if switch_var and switch_cases:
        service_lines.append(f"    // PHP switch(${switch_var}) cases: {switch_cases}")
        service_lines.append(f"    const {switch_var} = input.{switch_var} ?? \"\";")
        service_lines.append("    switch (" + switch_var + ") {")
        for c in switch_cases:
            service_lines.append(f"      case \"{c}\": {{")
            service_lines.append("        // TODO: map this case to the equivalent model/service call")
            service_lines.append("        break;")
            service_lines.append("      }")
        service_lines.append("      default: {")
        service_lines.append("        // TODO: default behavior (PHP may omit default)")
        service_lines.append("        break;")
        service_lines.append("      }")
        service_lines.append("    }")
    else:
        service_lines.append("    // TODO: no switch detected, implement sequential logic")
    service_lines.append("")
    service_lines.append("    // TODO: return payload aligned to PHP response schema")
    service_lines.append("    return { status: true, message: \"TODO\", data: null, response_code: 200 };")
    service_lines.append("  }")
    service_lines.append("}")
    service_ts = "\n".join(service_lines) + "\n"

    # Controller
    controller_lines: List[str] = []
    controller_lines.append("import type { Request, Response, NextFunction } from \"express\";")
    controller_lines.append(f"import type {{ {to_pascal(name_base)}Input }} from \"../types/{name_base}.types\";")
    controller_lines.append(f"import {{ {to_pascal(name_base)}Service }} from \"../services/{name_base}.service\";")
    controller_lines.append("")
    controller_lines.append(f"export class {to_pascal(name_base)}Controller {{")
    controller_lines.append(f"  private readonly service = new {to_pascal(name_base)}Service();")
    controller_lines.append("")
    controller_lines.append("  /**")
    controller_lines.append(f"   * Route: {http_method} {route_path}")
    controller_lines.append("   * Source: generated from extracted PHP method + analysis.json")
    if self_consts:
        controller_lines.append(f"   * PHP references constants: {self_consts}")
    controller_lines.append("   */")
    controller_lines.append("  public handler = async (req: Request, res: Response, next: NextFunction) => {")
    controller_lines.append("    try {")
    controller_lines.append("      // TODO: add auth/permission checks (PHP likely uses _permiss or similar)")
    controller_lines.append("")
    if http_method == "GET":
        controller_lines.append("      const input: " + to_pascal(name_base) + "Input = {")
        for k in inputs.get("get", []):
            controller_lines.append(f"        {k}: typeof req.query.{k} === \"string\" ? req.query.{k} : undefined,")
        if not inputs.get("get", []):
            controller_lines.append("        // TODO: map query params")
        controller_lines.append("      };")
    else:
        controller_lines.append("      const input: " + to_pascal(name_base) + "Input = {")
        controller_lines.append("        // TODO: map body/params")
        controller_lines.append("      };")
    controller_lines.append("")
    controller_lines.append("      const result = await this.service.execute(input);")
    controller_lines.append("      const code = typeof result.response_code === \"number\" ? result.response_code : 200;")
    controller_lines.append("      return res.status(code).json(result);")
    controller_lines.append("    } catch (err) {")
    controller_lines.append("      return next(err);")
    controller_lines.append("    }")
    controller_lines.append("  };")
    controller_lines.append("}")
    controller_ts = "\n".join(controller_lines) + "\n"

    # semantic.md
    semantic_md_lines: List[str] = []
    semantic_md_lines.append("# Semantic Migration Notes")
    semantic_md_lines.append("")
    semantic_md_lines.append("## Endpoint")
    semantic_md_lines.append(f"- {http_method} `{route_path}`")
    semantic_md_lines.append("")
    semantic_md_lines.append("## PHP inputs detected")
    semantic_md_lines.append(f"- $this->get(): {inputs.get('get', [])}")
    semantic_md_lines.append(f"- $this->post(): {inputs.get('post', [])}")
    semantic_md_lines.append("")
    semantic_md_lines.append("## PHP dependencies")
    semantic_md_lines.append(f"- Models loaded: {models_loaded}")
    semantic_md_lines.append(f"- Model calls (coarse): {model_calls}")
    semantic_md_lines.append(f"- Model assignments (parsed): {model_assignments}")
    semantic_md_lines.append("")
    semantic_md_lines.append("## Control flow")
    semantic_md_lines.append(f"- switch var: {switch_var}")
    semantic_md_lines.append(f"- cases: {switch_cases}")
    semantic_md_lines.append("")
    semantic_md_lines.append("## Responses / codes / messages")
    semantic_md_lines.append(f"- REST_Controller codes found: {rest_codes}")
    semantic_md_lines.append(f"- messages found: {messages}")
    semantic_md_lines.append("")
    semantic_md_lines.append("## Migration TODOs")
    semantic_md_lines.append("- Definir capa de datos en Node y reemplazar modelos CI.")
    semantic_md_lines.append("- Replicar reglas de permisos y auth (ej: _permiss).")
    semantic_md_lines.append("- Replicar response schema exacto y status codes por rama.")
    semantic_md_lines.append("")
    semantic_md = "\n".join(semantic_md_lines) + "\n"

    return TranspileResult(
        controller_ts=controller_ts,
        service_ts=service_ts,
        types_ts=types_ts,
        semantic_md=semantic_md,
    )


def to_pascal(s: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", s)
    parts = [p for p in parts if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Endpoint"

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TranslationResult:
    draft_ts: str
    notes_md: str


def _extract_switch_cases(method_text: str) -> Tuple[Optional[str], List[Tuple[str, str]]]:
    """
    Busca un switch($var) y extrae cases con el bloque hasta break; o hasta el siguiente case/default.
    Retorna: (switch_var, [(case_value, case_body_php), ...])
    """
    text = method_text or ""
    m = re.search(r"switch\s*\(\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*{", text)
    if not m:
        return None, []

    switch_var = m.group(1)
    start = m.end()

    # Captura cases "case '1': .... break;" de forma aproximada
    cases: List[Tuple[str, str]] = []
    case_iter = list(re.finditer(r"\bcase\s+['\"]?([^'\"]+)['\"]?\s*:", text[start:], flags=re.IGNORECASE))
    if not case_iter:
        return switch_var, []

    # offsets relativos al texto[start:]
    for i, cm in enumerate(case_iter):
        case_val = cm.group(1)
        case_body_start = start + cm.end()

        if i + 1 < len(case_iter):
            case_body_end = start + case_iter[i + 1].start()
        else:
            # hasta default o fin del switch
            dm = re.search(r"\bdefault\s*:", text[case_body_start:], flags=re.IGNORECASE)
            if dm:
                case_body_end = case_body_start + dm.start()
            else:
                # fin del bloque switch: heurística, hasta la siguiente "}"
                close = text.find("}", case_body_start)
                case_body_end = close if close != -1 else len(text)

        body = text[case_body_start:case_body_end].strip()
        cases.append((case_val, body))

    return switch_var, cases


def _find_model_calls_in_block(block_php: str) -> List[str]:
    """
    $this->bankaccount_model->getlist_customer_bank('COMPLETED');
    Retorna strings "bankaccount_model.getlist_customer_bank(...)".
    """
    calls = re.findall(r"\$this->([A-Za-z_][A-Za-z0-9_]*)->([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\)\s*;", block_php, flags=re.DOTALL)
    out = []
    for model, fn, args in calls:
        args_one_line = " ".join(args.split())
        out.append(f"{model}.{fn}({args_one_line})")
    return out


def build_service_logic_draft(
    *,
    endpoint_path: str,
    http_method: str,
    method_name: str,
    analysis: Dict[str, Any],
    php_method_text: str,
    service_class_name: str,
    service_method_name: str,
) -> TranslationResult:
    """
    Genera un borrador TS a partir del análisis y del texto PHP.
    Enfoque A+B:
      - B: estructura determinística (inputs, switch cases, response codes).
      - A: heurísticas para model calls, default versioning, etc.
    """
    inputs_get = analysis.get("inputs", {}).get("get", []) or []
    inputs_post = analysis.get("inputs", {}).get("post", []) or []
    inputs_put = analysis.get("inputs", {}).get("put", []) or []
    inputs_delete = analysis.get("inputs", {}).get("delete", []) or []

    models_loaded = analysis.get("models_loaded", []) or []
    model_calls = analysis.get("model_calls", []) or []

    switch_var, cases = _extract_switch_cases(php_method_text)

    notes: List[str] = []
    notes.append(f"- Endpoint: {http_method} {endpoint_path}")
    notes.append(f"- PHP method: {method_name}")
    if models_loaded:
        notes.append(f"- Models loaded: {models_loaded}")
    if model_calls:
        notes.append(f"- Model calls detected: {model_calls}")
    if switch_var and cases:
        notes.append(f"- Switch detected on: ${switch_var} with cases: {[c[0] for c in cases]}")

    # Construcción TS
    draft: List[str] = []
    draft.append("/* eslint-disable @typescript-eslint/no-unused-vars */")
    draft.append("")
    draft.append("/**")
    draft.append(" * AUTO-DRAFT (A+B): Estructura basada en patrones del método PHP extraído.")
    draft.append(" * No es plug-and-play. Requiere intervención humana y capa DB real.")
    draft.append(" */")
    draft.append("")
    draft.append("export type ServiceInput = {")
    for k in sorted(set(inputs_get + inputs_post + inputs_put + inputs_delete)):
        draft.append(f"  {k}?: string;")
    draft.append("};")
    draft.append("")
    draft.append("export type ServiceOutput = unknown;")
    draft.append("")
    draft.append(f"export class {service_class_name} " + "{")
    draft.append(f"  public async {service_method_name}(input: ServiceInput): Promise<ServiceOutput> " + "{")
    draft.append("    // TODO: validar permisos/autorización equivalente a PHP ($user_permission, etc.)")
    draft.append("    // TODO: definir capa de datos (repositorio/DAO) para reemplazar modelos CodeIgniter")
    draft.append("")

    # Inputs
    if inputs_get:
        draft.append("    // Inputs (PHP $this->get -> Node req.query)")
        for k in inputs_get:
            draft.append(f"    const {k} = input.{k};")
        draft.append("")
    if inputs_post:
        draft.append("    // Inputs (PHP $this->post -> Node req.body)")
        for k in inputs_post:
            draft.append(f"    const {k} = input.{k};")
        draft.append("")
    if inputs_put:
        draft.append("    // Inputs (PHP $this->put -> Node req.body)")
        for k in inputs_put:
            draft.append(f"    const {k} = input.{k};")
        draft.append("")
    if inputs_delete:
        draft.append("    // Inputs (PHP $this->delete -> Node req.query/params según API)")
        for k in inputs_delete:
            draft.append(f"    const {k} = input.{k};")
        draft.append("")

    # Switch -> Node
    if switch_var and cases:
        draft.append(f"    // PHP switch (${switch_var}) traducido a estructura Node")
        draft.append(f"    const {switch_var} = input.{switch_var};")
        draft.append("    let result: unknown = [];")
        draft.append("    switch (" + (switch_var) + ") {")
        for case_val, case_body in cases:
            draft.append(f"      case '{case_val}': " + "{")
            calls = _find_model_calls_in_block(case_body)
            if calls:
                for c in calls:
                    draft.append(f"        // PHP: {c}")
            draft.append("        // TODO: implementar llamada equivalente (repositorio/DB)")
            draft.append("        break;")
            draft.append("      }")
        draft.append("      default: {")
        draft.append("        // TODO: default behavior (en PHP puede ser case '0' u otro flujo)")
        draft.append("        break;")
        draft.append("      }")
        draft.append("    }")
        draft.append("")
        draft.append("    // TODO: alinear estructura de respuesta con PHP ($this->response)")
        draft.append("    return { data: result };")
    else:
        draft.append("    // TODO: no se detectó switch. Implementar lógica basada en el método PHP.")
        if model_calls:
            draft.append("    // Model calls detectadas (referencia):")
            for mc in model_calls:
                draft.append(f"    // - {mc}")
        draft.append("    return {};")

    draft.append("  }")
    draft.append("}")
    draft.append("")

    notes_md = "\n".join(["# Translation Notes (A+B)", ""] + notes + [""])
    return TranslationResult(draft_ts="\n".join(draft), notes_md=notes_md)

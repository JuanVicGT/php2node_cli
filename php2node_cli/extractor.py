from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .utils import read_text


@dataclass
class MethodExtractResult:
    found: bool
    method_name: str
    extracted: Optional[str]
    start_line: Optional[int]
    end_line: Optional[int]
    notes: List[str]


def _scan_braces_php(source: str, start_idx: int) -> Optional[int]:
    """
    Scans from start_idx and returns index of the matching closing brace for the method body.
    Lightweight state machine to skip strings and comments.
    """
    i = start_idx
    n = len(source)

    # Move to first '{'
    while i < n and source[i] != "{":
        i += 1
    if i >= n:
        return None

    brace = 0
    in_squote = False
    in_dquote = False
    in_line_comment = False
    in_block_comment = False
    escape = False

    while i < n:
        ch = source[i]
        nxt = source[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_squote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_squote = False
            i += 1
            continue

        if in_dquote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_dquote = False
            i += 1
            continue

        # comments start
        if ch == "/" and nxt == "/":
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if ch == "#":
            in_line_comment = True
            i += 1
            continue

        # strings start
        if ch == "'":
            in_squote = True
            i += 1
            continue
        if ch == '"':
            in_dquote = True
            i += 1
            continue

        # braces
        if ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
            if brace == 0:
                return i

        i += 1

    return None


def extract_method_block(controller_file: Path, method_name: str) -> MethodExtractResult:
    src = read_text(controller_file)
    notes: List[str] = []

    pat = re.compile(rf"\bfunction\s+{re.escape(method_name)}\s*\(", re.IGNORECASE)
    m = pat.search(src)
    if not m:
        return MethodExtractResult(False, method_name, None, None, None, ["Method signature not found"])

    start_sig = m.start()
    end_brace = _scan_braces_php(src, m.end())
    if end_brace is None:
        return MethodExtractResult(False, method_name, None, None, None, ["Could not match braces for method body"])

    extracted = src[start_sig : end_brace + 1]

    start_line = src.count("\n", 0, start_sig) + 1
    end_line = src.count("\n", 0, end_brace) + 1

    return MethodExtractResult(True, method_name, extracted, start_line, end_line, notes)


def detect_dependencies(method_src: str) -> dict:
    """
    Heuristics:
      $this->load->model / helper / library
      $this->get() / $this->post() / $this->put() / $this->delete()
    """
    def findall(p):
        return sorted(set(re.findall(p, method_src, flags=re.IGNORECASE)))

    return {
        "models": findall(r"\$this->load->model\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        "helpers": findall(r"\$this->load->helper\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        "libraries": findall(r"\$this->load->library\(\s*['\"]([^'\"]+)['\"]\s*\)"),
        "inputs_get": bool(re.search(r"\$this->get\(", method_src, flags=re.IGNORECASE)),
        "inputs_post": bool(re.search(r"\$this->post\(", method_src, flags=re.IGNORECASE)),
        "inputs_put": bool(re.search(r"\$this->put\(", method_src, flags=re.IGNORECASE)),
        "inputs_delete": bool(re.search(r"\$this->delete\(", method_src, flags=re.IGNORECASE)),
    }


def analyze_php_method(method_text: str) -> Dict[str, Any]:
    """
    Heurística: analiza el método PHP extraído para inferir inputs, responses, switch cases y llamadas a modelo.
    No intenta ejecutar ni interpretar PHP, solo extrae patrones.
    """
    text = method_text or ""

    def find_inputs(fn_name: str) -> List[str]:
        return sorted(set(re.findall(rf"\$this->{fn_name}\(\s*['\"]([^'\"]+)['\"]\s*\)", text)))

    inputs_get = find_inputs("get")
    inputs_post = find_inputs("post")
    inputs_put = find_inputs("put")
    inputs_delete = find_inputs("delete")

    models = sorted(set(re.findall(r"\$this->load->model\(\s*['\"]([^'\"]+)['\"]\s*\)", text)))

    model_calls = re.findall(r"\$this->([A-Za-z_][A-Za-z0-9_]*)->([A-Za-z_][A-Za-z0-9_]*)\s*\(", text)
    model_calls_fmt = sorted(set([f"{m}.{fn}" for (m, fn) in model_calls]))

    response_codes = sorted(set(re.findall(r"REST_Controller::HTTP_([A-Z_]+)", text)))
    switch_vars = re.findall(r"switch\s*\(\s*\$([A-Za-z_][A-Za-z0-9_]*)\s*\)", text)
    cases = re.findall(r"case\s+['\"]?([^'\"]+)['\"]?\s*:", text)
    has_default = bool(re.search(r"\bdefault\s*:", text))
    self_consts = sorted(set(re.findall(r"self::([A-Za-z_][A-Za-z0-9_]*)", text)))
    messages = sorted(set(re.findall(r"'message'\s*=>\s*'([^']+)'", text)))

    return {
        "inputs": {"get": inputs_get, "post": inputs_post, "put": inputs_put, "delete": inputs_delete},
        "models_loaded": models,
        "model_calls": model_calls_fmt,
        "responses": {"rest_codes": response_codes, "messages": messages},
        "control_flow": {"switch_vars": switch_vars, "cases": cases, "has_default": has_default},
        "constants": {"self": self_consts},
    }

from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple


VALID_HTTP = {"GET", "POST", "PUT", "DELETE"}


def norm_http(method: str) -> str:
    m = (method or "").strip().upper()
    if m not in VALID_HTTP:
        raise ValueError(f"Invalid --http-method '{method}'. Must be one of {sorted(VALID_HTTP)}")
    return m


def norm_endpoint_path(p: str) -> str:
    p = (p or "").strip()
    p = p.lstrip("/")
    p = p.rstrip("/")
    return p


def norm_version(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = v.strip().lower()
    if not v:
        return None
    if not v.startswith("v"):
        v = "v" + v
    return v


def safe_slug(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "item"


def endpoint_key(version: str, http: str, endpoint_path: str) -> str:
    base = f"{version}_{http}_{endpoint_path}"
    slug = safe_slug(base)
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{slug}_{h}"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_text(p: Path, text: str) -> None:
    ensure_dir(p.parent)
    p.write_text(text, encoding="utf-8")


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")



def camel_case(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip()
    if not s:
        return s
    parts = s.split()
    out = parts[0].lower() + "".join(w.capitalize() for w in parts[1:])
    return out


def pascal_case(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", " ", s).strip()
    if not s:
        return s
    return "".join(w.capitalize() for w in s.split())


def normalize_controller_filename(controller: str) -> str:
    c = (controller or "").strip()
    if not c.lower().endswith(".php"):
        c += ".php"
    return c


def find_php_controllers_root(app_root: Path) -> Path:
    return app_root / "application" / "controllers"


@dataclass
class FileProbeResult:
    found: bool
    path: Optional[Path]
    tried: list[str]
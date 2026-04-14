from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .utils import ensure_dir, write_text, camel_case, pascal_case


@dataclass
class NestScaffoldPaths:
    module_file: Path
    controller_file: Path
    service_file: Path
    query_dto_file: Path
    body_dto_file: Path
    params_dto_file: Path
    response_interface_file: Path


def _sanitize_ts_field(name: str) -> str:
    value = (name or "").strip()
    value = value.replace("-", "_").replace(" ", "_")
    value = re.sub(r"[^a-zA-Z0-9_]", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")

    if not value:
        return "undefined_field"

    if value[0].isdigit():
        value = f"field_{value}"

    return value


def _unique_fields(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen = set()

    for item in values:
        field_name = _sanitize_ts_field(str(item))
        if field_name not in seen:
            seen.add(field_name)
            cleaned.append(field_name)

    return cleaned


def _extract_route_params(route_path: str) -> list[str]:
    raw = re.findall(r":([a-zA-Z_][a-zA-Z0-9_]*)", route_path or "")
    return _unique_fields(raw)


def _normalize_input_items(items: list) -> list[str]:
    normalized: list[str] = []

    for item in items or []:
        if isinstance(item, dict):
            name = item.get("name") or item.get("key") or item.get("field") or item.get("param")
            if name:
                normalized.append(str(name))
        else:
            normalized.append(str(item))

    return _unique_fields(normalized)


def _extract_input_groups(
    analysis_data: dict | None,
    route_path: str,
) -> tuple[list[str], list[str], list[str]]:
    if not analysis_data:
        return [], [], _extract_route_params(route_path)

    inputs = analysis_data.get("inputs", {}) or {}

    query_fields = _unique_fields(
        _normalize_input_items(inputs.get("get", []) or [])
        + _normalize_input_items(inputs.get("delete", []) or [])
    )

    body_fields = _unique_fields(
        _normalize_input_items(inputs.get("post", []) or [])
        + _normalize_input_items(inputs.get("put", []) or [])
    )

    params_fields = _extract_route_params(route_path)

    return query_fields, body_fields, params_fields


def _build_dto_properties(fields: list[str]) -> str:
    if not fields:
        return ""

    return "\n".join([f"  {field}?: unknown;" for field in fields])


def _merge_dto_fields(existing_content: str, class_name: str, new_fields: list[str]) -> str:
    if not new_fields:
        return existing_content

    class_pattern = rf"(export class {re.escape(class_name)} \{{)(.*?)(\n\}})"
    match = re.search(class_pattern, existing_content, flags=re.DOTALL)

    if not match:
        return existing_content

    class_start, class_body, class_end = match.groups()

    existing_fields = set(
        re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\?\s*:\s*unknown;", class_body, flags=re.MULTILINE)
    )
    fields_to_add = [f for f in new_fields if f not in existing_fields]

    if not fields_to_add:
        return existing_content

    addition = "\n" + "\n".join([f"  {field}?: unknown;" for field in fields_to_add])

    new_class_body = class_body.rstrip() + addition + "\n"
    new_class_block = class_start + new_class_body + class_end

    return re.sub(class_pattern, new_class_block, existing_content, count=1, flags=re.DOTALL)


def _extract_response_parts(analysis_data: dict | None) -> tuple[list[str], list[str], list[str]]:
    if not analysis_data:
        return [], [], []

    responses = analysis_data.get("responses", {}) or {}

    raw_codes = responses.get("rest_codes", []) or []
    raw_messages = responses.get("messages", []) or []

    raw_data_fields = responses.get("data_fields", []) or analysis_data.get("data_fields", []) or []

    if isinstance(raw_data_fields, dict):
        raw_data_fields = list(raw_data_fields.keys())

    normalized_codes = []
    seen_codes = set()
    for item in raw_codes:
        code = str(item).strip()
        if code and code not in seen_codes:
            seen_codes.add(code)
            normalized_codes.append(code)

    normalized_messages = []
    seen_messages = set()
    for item in raw_messages:
        message = str(item).strip()
        if message and message not in seen_messages:
            seen_messages.add(message)
            normalized_messages.append(message)

    normalized_data_fields = _normalize_input_items(raw_data_fields if isinstance(raw_data_fields, list) else [])

    return normalized_codes, normalized_messages, normalized_data_fields


def _build_response_interface(
    interface_name: str,
    status_type_name: str,
    response_codes: list[str],
    response_messages: list[str],
    response_data_fields: list[str],
    http_method: str,
    route_path: str,
    handler_name: str,
) -> str:
    if response_codes:
        union_values = " | ".join([f'"{code}"' for code in response_codes])
        status_type_ts = f"export type {status_type_name} = {union_values};"
    else:
        status_type_ts = f"export type {status_type_name} = string;"

    lines = []
    lines.append(status_type_ts)
    lines.append("")
    lines.append(f"export interface {interface_name} {{")
    lines.append("  /**")
    lines.append(f"   * Endpoint: {http_method} {route_path}")
    lines.append(f"   * Source PHP method: {handler_name}")
    lines.append("   */")
    lines.append(f"  status: {status_type_name};")

    if response_messages:
        lines.append("  /**")
        lines.append("   * Messages detected in PHP:")
        for msg in response_messages:
            lines.append(f"   * - {msg}")
        lines.append("   */")

    lines.append("  message?: string;")
    lines.append("  data?: unknown;")

    for field in response_data_fields:
        lines.append(f"  {field}?: unknown;")

    lines.append("}")

    return "\n".join(lines) + "\n"


def _merge_response_interface(
    existing_content: str,
    interface_name: str,
    status_type_name: str,
    response_codes: list[str],
    response_data_fields: list[str],
) -> str:
    current = existing_content

    existing_codes = re.findall(r'"([^"]+)"', current)
    merged_codes = []
    seen_codes = set()

    for code in existing_codes + response_codes:
        if code not in seen_codes:
            seen_codes.add(code)
            merged_codes.append(code)

    if merged_codes:
        union_values = " | ".join([f'"{code}"' for code in merged_codes])
        current = re.sub(
            rf"export type {re.escape(status_type_name)} = .*?;",
            f"export type {status_type_name} = {union_values};",
            current,
            count=1,
            flags=re.DOTALL,
        )

    interface_pattern = rf"(export interface {re.escape(interface_name)} \{{)(.*?)(\n\}})"
    match = re.search(interface_pattern, current, flags=re.DOTALL)

    if not match:
        return current

    interface_start, interface_body, interface_end = match.groups()

    existing_fields = set(
        re.findall(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\?\s*:\s*unknown;", interface_body, flags=re.MULTILINE)
    )

    fields_to_add = [f for f in response_data_fields if f not in existing_fields]

    if not fields_to_add:
        return current

    addition = "\n" + "\n".join([f"  {field}?: unknown;" for field in fields_to_add])
    new_interface_body = interface_body.rstrip() + addition + "\n"
    new_interface_block = interface_start + new_interface_body + interface_end

    return re.sub(interface_pattern, new_interface_block, current, count=1, flags=re.DOTALL)


def _build_service_guidance(
    analysis_data: dict | None,
    response_codes: list[str],
    response_messages: list[str],
) -> str:
    lines: list[str] = []

    model_calls = []
    models = []
    helpers = []
    libraries = []

    if analysis_data:
        model_calls = analysis_data.get("model_calls", []) or []
        models = analysis_data.get("models_loaded", []) or analysis_data.get("models", []) or []
        helpers = analysis_data.get("helpers", []) or []
        libraries = analysis_data.get("libraries", []) or []

    lines.append("    // Migration guidance")
    if model_calls:
        lines.append("    // PHP model calls detected:")
        for call in model_calls:
            lines.append(f"    // - {call}")

    if models:
        lines.append("    // Models loaded:")
        for model in models:
            lines.append(f"    // - {model}")

    if helpers:
        lines.append("    // Helpers detected:")
        for helper in helpers:
            lines.append(f"    // - {helper}")

    if libraries:
        lines.append("    // Libraries detected:")
        for library in libraries:
            lines.append(f"    // - {library}")

    if response_codes:
        lines.append("    // Possible response statuses:")
        for code in response_codes:
            lines.append(f"    // - {code}")

    if response_messages:
        lines.append("    // Possible response messages:")
        for msg in response_messages:
            lines.append(f'    // - "{msg}"')

    lines.append("    // TODO 1: map input to repository/service calls")
    lines.append("    // TODO 2: port PHP validation and branching logic")
    lines.append("    // TODO 3: map success and error responses to the response contract")

    return "\n".join(lines) + "\n"


def _build_placeholder_return(
    response_codes: list[str],
    response_messages: list[str],
) -> str:
    default_status = response_codes[0] if response_codes else "TODO_STATUS"
    default_message = response_messages[0] if response_messages else "TODO: map success message"

    return (
        "    return {\n"
        f'      status: "{default_status}",\n'
        f'      message: "{default_message}",\n'
        "      data: undefined,\n"
        "    };\n"
    )


def generate_nest_scaffold(
    out_node_dir: Path,
    http_method: str,
    route_path: str,
    name_base: str,
    handler_name: str,
    analysis_data: dict | None = None,
) -> NestScaffoldPaths:

    module_root = out_node_dir / "modules" / name_base

    controllers_dir = module_root / "controllers"
    services_dir = module_root / "services"
    dto_dir = module_root / "dto"
    interfaces_dir = module_root / "interfaces"

    ensure_dir(module_root)
    ensure_dir(controllers_dir)
    ensure_dir(services_dir)
    ensure_dir(dto_dir)
    ensure_dir(interfaces_dir)

    controller_file = controllers_dir / f"{name_base}.controller.ts"
    service_file = services_dir / f"{name_base}.service.ts"

    query_dto_file = dto_dir / f"{name_base}.query.dto.ts"
    body_dto_file = dto_dir / f"{name_base}.body.dto.ts"
    params_dto_file = dto_dir / f"{name_base}.params.dto.ts"

    response_interface_file = interfaces_dir / f"{name_base}.response.ts"

    module_file = module_root / f"{name_base}.module.ts"

    class_base = pascal_case(name_base)

    controller_class = f"{class_base}Controller"
    service_class = f"{class_base}Service"
    module_class = f"{class_base}Module"

    query_dto_class = f"{class_base}QueryDto"
    body_dto_class = f"{class_base}BodyDto"
    params_dto_class = f"{class_base}ParamsDto"

    response_interface_name = f"{class_base}Response"
    response_status_type_name = f"{class_base}ResponseStatus"

    handler = camel_case(handler_name)

    hm = http_method.upper()

    decorator_map = {
        "GET": "Get",
        "POST": "Post",
        "PUT": "Put",
        "DELETE": "Delete",
    }

    nest_decorator = decorator_map.get(hm, "Get")

    include_body = hm in {"POST", "PUT"}
    body_import = ", Body" if include_body else ""
    body_param = ""
    body_call = ""

    if include_body:
        body_param = f",\n    @Body() body: {body_dto_class}"
        body_call = "\n      body,"

    dependencies = ""

    if analysis_data:
        models = analysis_data.get("models_loaded", []) or analysis_data.get("models", [])
        helpers = analysis_data.get("helpers", [])
        libraries = analysis_data.get("libraries", [])
        model_calls = analysis_data.get("model_calls", [])

        if models or helpers or libraries or model_calls:
            lines = []
            lines.append("    /**")
            lines.append("     * PHP dependencies detected:")

            for m in models:
                lines.append(f"     * - model: {m}")

            for h in helpers:
                lines.append(f"     * - helper: {h}")

            for l in libraries:
                lines.append(f"     * - library: {l}")

            for c in model_calls:
                lines.append(f"     * - model_call: {c}")

            lines.append("     */")
            dependencies = "\n" + "\n".join(lines) + "\n"

    query_fields, body_fields, params_fields = _extract_input_groups(
        analysis_data=analysis_data,
        route_path=route_path,
    )

    response_codes, response_messages, response_data_fields = _extract_response_parts(analysis_data)
    service_guidance = _build_service_guidance(
        analysis_data=analysis_data,
        response_codes=response_codes,
        response_messages=response_messages,
    )
    placeholder_return = _build_placeholder_return(
        response_codes=response_codes,
        response_messages=response_messages,
    )

    query_properties = _build_dto_properties(query_fields)
    body_properties = _build_dto_properties(body_fields)
    params_properties = _build_dto_properties(params_fields)

    query_dto_comment = f"""  /**
   * Endpoint:
   * {hm} {route_path}
   * Source PHP method:
   * {handler_name}
   * Source group:
   * query
   */
"""

    body_dto_comment = f"""  /**
   * Endpoint:
   * {hm} {route_path}
   * Source PHP method:
   * {handler_name}
   * Source group:
   * body
   */
"""

    params_dto_comment = f"""  /**
   * Endpoint:
   * {hm} {route_path}
   * Source PHP method:
   * {handler_name}
   * Source group:
   * params
   */
"""

    query_dto_ts = f"""export class {query_dto_class} {{
{query_dto_comment}{query_properties if query_properties else ""}
}}
"""

    body_dto_ts = f"""export class {body_dto_class} {{
{body_dto_comment}{body_properties if body_properties else ""}
}}
"""

    params_dto_ts = f"""export class {params_dto_class} {{
{params_dto_comment}{params_properties if params_properties else ""}
}}
"""

    response_interface_ts = _build_response_interface(
        interface_name=response_interface_name,
        status_type_name=response_status_type_name,
        response_codes=response_codes,
        response_messages=response_messages,
        response_data_fields=response_data_fields,
        http_method=hm,
        route_path=route_path,
        handler_name=handler_name,
    )

    controller_ts = f"""import {{ Controller, {nest_decorator}, Query, Param{body_import} }} from "@nestjs/common";
import {{ {service_class} }} from "../services/{name_base}.service";
import {{ {query_dto_class} }} from "../dto/{name_base}.query.dto";
import {{ {body_dto_class} }} from "../dto/{name_base}.body.dto";
import {{ {params_dto_class} }} from "../dto/{name_base}.params.dto";
import type {{ {response_interface_name} }} from "../interfaces/{name_base}.response";

@Controller("{route_path.strip('/')}")
export class {controller_class} {{

  constructor(private readonly service: {service_class}) {{}}

  @{nest_decorator}()
  async {handler}(
    @Query() query: {query_dto_class}{body_param},
    @Param() params: {params_dto_class},
  ): Promise<{response_interface_name}> {{

    return this.service.{handler}({{
      query,
      params,{body_call}
    }});

  }}
}}
"""

    service_ts = f"""import {{ Injectable }} from "@nestjs/common";
import type {{ {response_interface_name} }} from "../interfaces/{name_base}.response";

@Injectable()
export class {service_class} {{

  async {handler}(_input: unknown): Promise<{response_interface_name}> {{
{dependencies}{service_guidance}{placeholder_return}
  }}

}}
"""

    module_ts = f"""import {{ Module }} from "@nestjs/common";

import {{ {controller_class} }} from "./controllers/{name_base}.controller";
import {{ {service_class} }} from "./services/{name_base}.service";

@Module({{
  controllers: [{controller_class}],
  providers: [{service_class}],
}})
export class {module_class} {{}}
"""

    if not controller_file.exists():
        write_text(controller_file, controller_ts)
    else:
        content = controller_file.read_text(encoding="utf-8")

        if f"async {handler}(" not in content:
            handler_block = f"""

  @{nest_decorator}()
  async {handler}(
    @Query() query: {query_dto_class}{body_param},
    @Param() params: {params_dto_class},
  ): Promise<{response_interface_name}> {{

    return this.service.{handler}({{
      query,
      params,{body_call}
    }});

  }}
"""

            stripped = content.rstrip()
            if stripped.endswith("}"):
                stripped = stripped[:-1].rstrip()

            content = stripped + handler_block + "\n}\n"
            write_text(controller_file, content)

    if not service_file.exists():
        write_text(service_file, service_ts)
    else:
        content = service_file.read_text(encoding="utf-8")

        if f"async {handler}(" not in content:
            method_block = f"""

  async {handler}(_input: unknown): Promise<{response_interface_name}> {{
{dependencies}{service_guidance}{placeholder_return}
  }}
"""

            stripped = content.rstrip()
            if stripped.endswith("}"):
                stripped = stripped[:-1].rstrip()

            content = stripped + method_block + "\n}\n"
            write_text(service_file, content)

    if not query_dto_file.exists():
        write_text(query_dto_file, query_dto_ts)
    else:
        content = query_dto_file.read_text(encoding="utf-8")
        content = _merge_dto_fields(content, query_dto_class, query_fields)
        write_text(query_dto_file, content)

    if not body_dto_file.exists():
        write_text(body_dto_file, body_dto_ts)
    else:
        content = body_dto_file.read_text(encoding="utf-8")
        content = _merge_dto_fields(content, body_dto_class, body_fields)
        write_text(body_dto_file, content)

    if not params_dto_file.exists():
        write_text(params_dto_file, params_dto_ts)
    else:
        content = params_dto_file.read_text(encoding="utf-8")
        content = _merge_dto_fields(content, params_dto_class, params_fields)
        write_text(params_dto_file, content)

    if not response_interface_file.exists():
        write_text(response_interface_file, response_interface_ts)
    else:
        content = response_interface_file.read_text(encoding="utf-8")
        content = _merge_response_interface(
            existing_content=content,
            interface_name=response_interface_name,
            status_type_name=response_status_type_name,
            response_codes=response_codes,
            response_data_fields=response_data_fields,
        )
        write_text(response_interface_file, content)

    if not module_file.exists():
        write_text(module_file, module_ts)

    return NestScaffoldPaths(
        module_file=module_file,
        controller_file=controller_file,
        service_file=service_file,
        query_dto_file=query_dto_file,
        body_dto_file=body_dto_file,
        params_dto_file=params_dto_file,
        response_interface_file=response_interface_file,
    )
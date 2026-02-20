from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .utils import ensure_dir, write_text, camel_case, pascal_case


@dataclass
class NodeScaffoldPaths:
    routes_file: Path
    controller_file: Path
    service_file: Path
    types_file: Path


def generate_scaffold(
    out_node_dir: Path,
    http_method: str,
    route_path: str,
    name_base: str,
    handler_name: str,
) -> NodeScaffoldPaths:
    """
    out_node_dir/
      routes/<name>.routes.ts
      controllers/<name>.controller.ts
      services/<name>.service.ts
      types/<name>.types.ts
    """
    routes_dir = out_node_dir / "routes"
    controllers_dir = out_node_dir / "controllers"
    services_dir = out_node_dir / "services"
    types_dir = out_node_dir / "types"

    ensure_dir(routes_dir)
    ensure_dir(controllers_dir)
    ensure_dir(services_dir)
    ensure_dir(types_dir)

    route_file = routes_dir / f"{name_base}.routes.ts"
    controller_file = controllers_dir / f"{name_base}.controller.ts"
    service_file = services_dir / f"{name_base}.service.ts"
    types_file = types_dir / f"{name_base}.types.ts"

    class_name = pascal_case(name_base) + "Controller"
    service_class = pascal_case(name_base) + "Service"
    handler = camel_case(handler_name)

    hm = http_method.upper()

    routes_ts = f"""import {{ Router }} from "express";
import {{ {class_name} }} from "../controllers/{name_base}.controller";

const router = Router();
const controller = new {class_name}();

/**
 * Route: {hm} {route_path}
 * TODO: add auth middleware, validation, and error handling strategy
 */
router.{hm.lower()}("{route_path}", controller.{handler});

export default router;
"""

    controller_ts = f"""import type {{ Request, Response, NextFunction }} from "express";
import {{ {service_class} }} from "../services/{name_base}.service";

export class {class_name} {{
  private readonly service = new {service_class}();

  /**
   * Handler: {hm} {route_path}
   * Source: methodBase = {handler_name}
   * TODO: map request params/query/body based on the extracted PHP method.
   */
  public {handler} = async (req: Request, res: Response, next: NextFunction) => {{
    try {{
      // TODO: extract inputs from req (query/body/params) and pass to service
      const result = await this.service.{handler}({{
        // TODO: define input contract
      }});

      // TODO: align response structure/status codes with current PHP behavior
      return res.status(200).json(result);
    }} catch (err) {{
      return next(err);
    }}
  }};
}}
"""

    service_ts = f"""export class {service_class} {{
  /**
   * TODO: implement business logic by porting from PHP method.
   * Do NOT invent rules here; keep TODOs explicit.
   */
  public async {handler}(_input: unknown): Promise<unknown> {{
    // TODO: translate model calls, helpers, libraries usage
    // TODO: handle DB access strategy for Node (not defined in scaffold)
    throw new Error("TODO: not implemented");
  }}
}}
"""

    types_ts = f"""/**
 * TODO: Define request/response types once you map the PHP contract.
 */

export type {pascal_case(name_base)}Input = unknown;
export type {pascal_case(name_base)}Output = unknown;
"""

    write_text(route_file, routes_ts)
    write_text(controller_file, controller_ts)
    write_text(service_file, service_ts)
    write_text(types_file, types_ts)

    return NodeScaffoldPaths(route_file, controller_file, service_file, types_file)

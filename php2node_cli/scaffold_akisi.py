"""
scaffold_akisi.py
=================
Genera el output de migración siguiendo el patrón del repositorio akisi_backend_nestjs.

Flujo A (por defecto) — controller → use-case:
  msa-<name>/src/
  ├── controllers/
  │   └── <entity>.controller.ts
  ├── use-cases/
  │   └── <handler>/
  │       └── <handler>.use-case.ts
  ├── <entity>.model.ts
  ├── app.module.ts
  └── main.ts

Flujo B — controller → service → use-cases (orquestación multi-paso):
  msa-<name>/src/
  ├── <entity>.controller.ts
  ├── <entity>.service.ts
  ├── <entity>.model.ts
  ├── app.module.ts
  └── main.ts
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .utils import ensure_dir, write_text, pascal_case, safe_slug


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses de resultado
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AkisiScaffoldPaths:
    ms_dir: Path
    controller_file: Path
    service_file: Path | None        # None en Flujo A
    use_case_file: Path | None       # None en Flujo B
    model_file: Path
    module_file: Path
    main_file: Path
    dockerfile: Path
    package_json: Path
    tsconfig_json: Path
    gateway_controller_patch: Path
    gateway_service_patch: Path
    docker_compose_patch: Path | None
    instrucciones_file: Path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "servicio"


def _snake(name: str) -> str:
    return _slug(name).replace("-", "_")


def _handler_slug(handler_name: str) -> str:
    """Convierte camelCase o snake_case a kebab-case para nombres de directorios."""
    s = re.sub(r"([A-Z])", r"-\1", handler_name).lower().lstrip("-")
    s = s.replace("_", "-")
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "handler"


def _detectar_campos_modelo(analysis_data: dict | None) -> list[dict]:
    if not analysis_data:
        return []

    inputs = analysis_data.get("inputs", {}) or {}
    todos: list[str] = []

    for grupo in ("get", "post", "put", "delete"):
        items = inputs.get(grupo, []) or []
        for item in items:
            if isinstance(item, dict):
                nombre = item.get("name") or item.get("key") or item.get("field") or ""
            else:
                nombre = str(item)
            nombre = nombre.strip()
            if nombre:
                todos.append(nombre)

    vistos: set[str] = set()
    unicos: list[str] = []
    for c in todos:
        if c not in vistos:
            vistos.add(c)
            unicos.append(c)

    return [_inferir_tipo_campo(n) for n in unicos]


def _inferir_tipo_campo(nombre: str) -> dict:
    n = nombre.lower()

    if any(k in n for k in ("monto", "amount", "precio", "price", "balance", "total", "saldo")):
        return {"name": nombre, "ts_type": "number", "sequelize_type": "DataType.DECIMAL(12, 2)", "nullable": True, "comment": "TODO: verificar precisión decimal"}
    if any(k in n for k in ("fecha", "date", "hora", "time", "created", "updated")):
        return {"name": nombre, "ts_type": "Date", "sequelize_type": "DataType.DATE", "nullable": True, "comment": "TODO: verificar formato de fecha"}
    if any(k in n for k in ("_id", "id_", "codigo", "code", "numero", "number", "count", "cantidad", "qty")):
        return {"name": nombre, "ts_type": "number", "sequelize_type": "DataType.INTEGER", "nullable": True, "comment": "TODO: verificar si es FK o PK"}
    if any(k in n for k in ("activo", "active", "estado", "status", "habilitado", "enabled")):
        return {"name": nombre, "ts_type": "string", "sequelize_type": "DataType.STRING(20)", "nullable": True, "comment": "TODO: considerar ENUM si los valores son fijos"}
    if any(k in n for k in ("descripcion", "description", "detalle", "detail", "nota", "note", "comentario")):
        return {"name": nombre, "ts_type": "string", "sequelize_type": "DataType.TEXT", "nullable": True, "comment": "TODO: verificar longitud máxima"}
    return {"name": nombre, "ts_type": "string", "sequelize_type": "DataType.STRING(255)", "nullable": True, "comment": "TODO: ajustar tipo y longitud"}


def _detectar_metodos_servicio(analysis_data: dict | None) -> list[str]:
    if not analysis_data:
        return []
    calls = analysis_data.get("model_calls", []) or []
    metodos: list[str] = []
    for call in calls:
        if "->" in str(call):
            metodo = str(call).split("->")[-1].strip()
            if metodo and metodo not in metodos:
                metodos.append(metodo)
    return metodos


def _detectar_responses(analysis_data: dict | None) -> tuple[list[str], list[str]]:
    if not analysis_data:
        return [], []
    responses = analysis_data.get("responses", {}) or {}
    codigos = [str(c) for c in (responses.get("rest_codes", []) or []) if c]
    mensajes = [str(m) for m in (responses.get("messages", []) or []) if m]
    return codigos, mensajes


# ─────────────────────────────────────────────────────────────────────────────
# Generadores de archivos TypeScript
# ─────────────────────────────────────────────────────────────────────────────

def _build_model(entity_class: str, entity_snake: str, campos: list[dict], table_name: str) -> str:
    lineas_campos = []
    for c in campos:
        lineas_campos.append(f"  // {c['comment']}")
        if c["nullable"]:
            lineas_campos.append(f"  @Column({{ type: {c['sequelize_type']}, allowNull: true }})")
        else:
            lineas_campos.append(f"  @Column({{ type: {c['sequelize_type']}, allowNull: false }})")
        lineas_campos.append(f"  {c['name']}?: {c['ts_type']};")
        lineas_campos.append("")

    campos_str = "\n".join(lineas_campos)

    return f"""import {{
  Table,
  Column,
  Model,
  DataType,
  CreatedAt,
  UpdatedAt,
  PrimaryKey,
  AutoIncrement,
}} from 'sequelize-typescript';

/**
 * Modelo: {entity_class}
 * Tabla : {table_name}
 *
 * AVISO: Este modelo fue generado automáticamente desde el análisis del PHP.
 * Si el modelo ya existe en @akisi/sequelize-models, eliminar este archivo
 * e importar desde el paquete compartido.
 */
@Table({{ tableName: '{table_name}', timestamps: true }})
export class {entity_class} extends Model {{

  @PrimaryKey
  @AutoIncrement
  @Column(DataType.INTEGER)
  id: number;

{campos_str}
  @CreatedAt
  @Column({{ field: 'creado_en' }})
  creadoEn: Date;

  @UpdatedAt
  @Column({{ field: 'actualizado_en' }})
  actualizadoEn: Date;

}}
"""


def _build_use_case(
    entity_class: str,
    entity_snake: str,
    ms_name_slug: str,
    http_method: str,
    handler_name: str,
    use_case_class: str,
    metodos_php: list[str],
    codigos_resp: list[str],
    mensajes_resp: list[str],
    analysis_data: dict | None,
) -> str:
    """Genera el use-case NestJS para Flujo A (controller → use-case directo)."""
    models_loaded = []
    helpers = []
    libraries = []
    if analysis_data:
        models_loaded = analysis_data.get("models_loaded", []) or []
        helpers = analysis_data.get("helpers", []) or []
        libraries = analysis_data.get("libraries", []) or []

    comentarios = ["    // ── Guía de migración desde PHP ────────────────────────────────────"]
    if models_loaded:
        comentarios.append("    // Modelos PHP detectados — importar desde @akisi/sequelize-models:")
        for m in models_loaded:
            comentarios.append(f"    //   - {m}")
    if metodos_php:
        comentarios.append("    // Llamadas a modelo detectadas:")
        for m in metodos_php:
            comentarios.append(f"    //   - {m}  → implementar lógica equivalente aquí")
    if helpers:
        comentarios.append("    // Helpers PHP detectados (reemplazar con utilidades Node):")
        for h in helpers:
            comentarios.append(f"    //   - {h}")
    if libraries:
        comentarios.append("    // Librerías PHP detectadas (evaluar equivalente en Node):")
        for l in libraries:
            comentarios.append(f"    //   - {l}")
    if codigos_resp:
        comentarios.append("    // Respuestas HTTP detectadas en PHP:")
        for c in codigos_resp:
            comentarios.append(f"    //   - HTTP {c}")
    if mensajes_resp:
        comentarios.append("    // Mensajes de respuesta detectados:")
        for m in mensajes_resp:
            comentarios.append(f"    //   - \"{m}\"")

    comentarios.append("    // ────────────────────────────────────────────────────────────────")
    comentarios.append("    // TODO 1: implementar lógica de negocio equivalente al PHP")
    comentarios.append("    // TODO 2: mapear inputs a llamadas al repositorio/modelo")
    comentarios.append("    // TODO 3: alinear códigos y mensajes de respuesta")

    guia = "\n".join(comentarios)

    return f"""import {{ Injectable }} from '@nestjs/common';
import {{ InjectModel }} from '@nestjs/sequelize';
import {{ {entity_class} }} from '../../{entity_snake}.model';

/**
 * UseCase: {use_case_class}
 * Flujo A — controller → use-case (sin service intermediario)
 * Microservicio: msa-{ms_name_slug}
 *
 * Generado automáticamente. Revisar la guía de migración antes de implementar.
 */
@Injectable()
export class {use_case_class} {{

  constructor(
    @InjectModel({entity_class})
    private readonly modelo: typeof {entity_class},
  ) {{}}

  /**
   * Método migrado desde PHP: {handler_name}
   * HTTP: {http_method}
   */
  async execute(input: unknown): Promise<unknown> {{
{guia}
    return null; // TODO: reemplazar con implementación real
  }}

}}
"""


def _build_service(
    entity_class: str,
    entity_snake: str,
    ms_name_slug: str,
    http_method: str,
    handler_name: str,
    metodos_php: list[str],
    codigos_resp: list[str],
    mensajes_resp: list[str],
    analysis_data: dict | None,
) -> str:
    """Genera el servicio NestJS para Flujo B (orquestación multi-paso)."""
    models_loaded = []
    helpers = []
    libraries = []
    if analysis_data:
        models_loaded = analysis_data.get("models_loaded", []) or []
        helpers = analysis_data.get("helpers", []) or []
        libraries = analysis_data.get("libraries", []) or []

    comentarios_migracion = ["    // ── Guía de migración desde PHP ────────────────────────────────────"]
    if models_loaded:
        comentarios_migracion.append("    // Modelos PHP detectados:")
        for m in models_loaded:
            comentarios_migracion.append(f"    //   - {m}")
    if metodos_php:
        comentarios_migracion.append("    // Llamadas a modelo detectadas:")
        for m in metodos_php:
            comentarios_migracion.append(f"    //   - {m}  → implementar lógica equivalente aquí")
    if helpers:
        comentarios_migracion.append("    // Helpers PHP detectados (reemplazar con utilidades Node):")
        for h in helpers:
            comentarios_migracion.append(f"    //   - {h}")
    if libraries:
        comentarios_migracion.append("    // Librerías PHP detectadas (evaluar equivalente en Node):")
        for l in libraries:
            comentarios_migracion.append(f"    //   - {l}")
    if codigos_resp:
        comentarios_migracion.append("    // Respuestas HTTP detectadas en PHP:")
        for c in codigos_resp:
            comentarios_migracion.append(f"    //   - HTTP {c}")
    if mensajes_resp:
        comentarios_migracion.append("    // Mensajes de respuesta detectados:")
        for m in mensajes_resp:
            comentarios_migracion.append(f"    //   - \"{m}\"")

    comentarios_migracion.append("    // ────────────────────────────────────────────────────────────────")
    comentarios_migracion.append("    // TODO 1: implementar lógica de negocio equivalente al PHP")
    comentarios_migracion.append("    // TODO 2: mapear inputs a llamadas al repositorio/modelo")
    comentarios_migracion.append("    // TODO 3: alinear códigos y mensajes de respuesta")
    comentarios_migracion.append("    // Flujo B — coordinar use-cases atómicos desde este service")

    guia = "\n".join(comentarios_migracion)

    return f"""import {{ Injectable }} from '@nestjs/common';
import {{ InjectModel }} from '@nestjs/sequelize';
import {{ {entity_class} }} from '../{entity_snake}.model';

/**
 * Servicio: {entity_class}Service
 * Flujo B — orquestación multi-paso (controller → service → use-cases)
 * Microservicio: msa-{ms_name_slug}
 *
 * Generado automáticamente. Revisar la guía de migración en cada método.
 */
@Injectable()
export class {entity_class}Service {{

  constructor(
    @InjectModel({entity_class})
    private readonly modelo: typeof {entity_class},
  ) {{}}

  /**
   * Método migrado desde PHP: {handler_name}
   * HTTP: {http_method}
   */
  async {handler_name}(input: unknown): Promise<unknown> {{
{guia}
    return null; // TODO: reemplazar con implementación real
  }}

}}
"""


def _build_controller_flujo_a(
    entity_class: str,
    entity_snake: str,
    ms_name_slug: str,
    http_method: str,
    route_path: str,
    handler_name: str,
    use_case_class: str,
    use_case_slug: str,
) -> str:
    """Genera el controller para Flujo A — inyecta use-case directamente."""
    hm = http_method.upper()
    decorator_map = {"GET": "Get", "POST": "Post", "PUT": "Put", "DELETE": "Delete"}
    decorator = decorator_map.get(hm, "Get")

    include_body = hm in {"POST", "PUT"}
    body_import = ", Body" if include_body else ""
    body_param = "\n    @Body() body: unknown," if include_body else ""
    body_arg = "\n      body," if include_body else ""

    use_case_import_path = f"../use-cases/{use_case_slug}/{use_case_slug}.use-case"

    return f"""import {{ Controller, {decorator}, Query, Param{body_import} }} from '@nestjs/common';
import {{ {use_case_class} }} from '{use_case_import_path}';

/**
 * Controller: {entity_class}Controller
 * Ruta base : {route_path}
 * Flujo A   : controller → use-case (sin service intermediario)
 * Microservicio: msa-{ms_name_slug}
 */
@Controller('{route_path.strip("/")}')
export class {entity_class}Controller {{

  constructor(private readonly useCase: {use_case_class}) {{}}

  @{decorator}()
  async {handler_name}(
    @Query() query: unknown,{body_param}
    @Param() params: unknown,
  ): Promise<unknown> {{
    return this.useCase.execute({{
      query,{body_arg}
      params,
    }});
  }}

}}
"""


def _build_controller_flujo_b(
    entity_class: str,
    entity_snake: str,
    ms_name_slug: str,
    http_method: str,
    route_path: str,
    handler_name: str,
) -> str:
    """Genera el controller para Flujo B — inyecta service."""
    hm = http_method.upper()
    decorator_map = {"GET": "Get", "POST": "Post", "PUT": "Put", "DELETE": "Delete"}
    decorator = decorator_map.get(hm, "Get")

    include_body = hm in {"POST", "PUT"}
    body_import = ", Body" if include_body else ""
    body_param = "\n    @Body() body: unknown," if include_body else ""
    body_arg = "\n      body," if include_body else ""

    return f"""import {{ Controller, {decorator}, Query, Param{body_import} }} from '@nestjs/common';
import {{ {entity_class}Service }} from '../{entity_snake}.service';

/**
 * Controller: {entity_class}Controller
 * Ruta base : {route_path}
 * Flujo B   : controller → service (orquestación multi-paso)
 * Microservicio: msa-{ms_name_slug}
 */
@Controller('{route_path.strip("/")}')
export class {entity_class}Controller {{

  constructor(private readonly service: {entity_class}Service) {{}}

  @{decorator}()
  async {handler_name}(
    @Query() query: unknown,{body_param}
    @Param() params: unknown,
  ): Promise<unknown> {{
    return this.service.{handler_name}({{
      query,{body_arg}
      params,
    }});
  }}

}}
"""


def _build_app_module(
    entity_class: str,
    entity_snake: str,
    ms_name_slug: str,
    flujo: str,
    use_case_class: str = "",
    use_case_slug: str = "",
    db_name: str = "billetera",
) -> str:
    """Genera el app.module.ts adaptado al flujo seleccionado."""
    if flujo == "A":
        provider_import = f"import {{ {use_case_class} }} from './use-cases/{use_case_slug}/{use_case_slug}.use-case';"
        controller_import = f"import {{ {entity_class}Controller }} from './controllers/{entity_snake}.controller';"
        provider_name = use_case_class
    else:
        provider_import = f"import {{ {entity_class}Service }} from './{entity_snake}.service';"
        controller_import = f"import {{ {entity_class}Controller }} from './{entity_snake}.controller';"
        provider_name = f"{entity_class}Service"

    return f"""import {{ Module }} from '@nestjs/common';
import {{ SequelizeModule }} from '@nestjs/sequelize';
import {{ {entity_class} }} from './{entity_snake}.model';
{controller_import}
{provider_import}

/**
 * Módulo raíz del microservicio msa-{ms_name_slug}
 * Flujo {flujo}
 */
@Module({{
  imports: [
    SequelizeModule.forRoot({{
      dialect: 'mysql',
      host: process.env.DB_HOST || 'mysql',
      port: parseInt(process.env.DB_PORT || '3306'),
      username: process.env.DB_USER || 'root',
      password: process.env.DB_PASSWORD || 'secret',
      database: process.env.DB_NAME || '{db_name}',
      models: [{entity_class}],
      autoLoadModels: true,
      synchronize: process.env.NODE_ENV !== 'production',
    }}),
    SequelizeModule.forFeature([{entity_class}]),
  ],
  controllers: [{entity_class}Controller],
  providers: [{provider_name}],
}})
export class AppModule {{}}
"""


def _build_main(ms_name_slug: str, port: int) -> str:
    return f"""import 'reflect-metadata';
import {{ NestFactory }} from '@nestjs/core';
import {{ AppModule }} from './app.module';

async function bootstrap() {{
  const app = await NestFactory.create(AppModule);
  await app.listen(process.env.PORT ?? {port}, '0.0.0.0');
  console.log(`msa-{ms_name_slug} corriendo en el puerto: ${{process.env.PORT ?? {port}}}`);
}}
bootstrap();
"""


def _build_package_json(ms_name_slug: str) -> str:
    return f"""{{
  "name": "msa-{ms_name_slug}",
  "version": "1.0.0",
  "scripts": {{
    "start:dev": "ts-node src/main.ts",
    "build": "tsc",
    "start": "node dist/main.js"
  }},
  "dependencies": {{
    "@nestjs/common": "^10.0.0",
    "@nestjs/core": "^10.0.0",
    "@nestjs/platform-express": "^10.0.0",
    "@nestjs/sequelize": "^10.0.0",
    "sequelize": "^6.35.0",
    "sequelize-typescript": "^2.1.6",
    "mysql2": "^3.6.0",
    "reflect-metadata": "^0.1.13",
    "rxjs": "^7.8.1"
  }},
  "devDependencies": {{
    "typescript": "^5.1.0",
    "ts-node": "^10.9.1",
    "@types/node": "^20.0.0",
    "@types/sequelize": "^4.28.20"
  }}
}}
"""


def _build_dockerfile(ms_name_slug: str, port: int) -> str:
    return f"""FROM node:20-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .
RUN npm run build

EXPOSE {port}

CMD ["npm", "run", "start"]
"""


def _build_tsconfig() -> str:
    return """{
  "compilerOptions": {
    "module": "commonjs",
    "declaration": true,
    "removeComments": true,
    "emitDecoratorMetadata": true,
    "experimentalDecorators": true,
    "allowSyntheticDefaultImports": true,
    "target": "ES2021",
    "sourceMap": true,
    "outDir": "./dist",
    "baseUrl": "./",
    "incremental": true,
    "skipLibCheck": true,
    "strictNullChecks": false
  }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Generadores de parches para el gateway (mdl-billetera)
# ─────────────────────────────────────────────────────────────────────────────

def _build_gateway_controller_patch(
    ms_name_slug: str,
    entity_snake: str,
    http_method: str,
    route_path: str,
    handler_name: str,
    port: int,
) -> str:
    hm = http_method.upper()
    decorator_map = {"GET": "Get", "POST": "Post", "PUT": "Put", "DELETE": "Delete"}
    decorator = decorator_map.get(hm, "Get")
    include_body = hm in {"POST", "PUT"}
    body_param = "\n  @Body() body: unknown," if include_body else ""
    body_arg = "\n      body," if include_body else ""

    return f"""// ══════════════════════════════════════════════════════════════════════
// PARCHE GATEWAY — msa-{ms_name_slug}
// Agregar este bloque en: mdl-billetera/src/app.controller.ts
//
// PASO 1: Agregar el decorador a la lista de imports de @nestjs/common:
//   {decorator}, (si no está ya importado)
//
// PASO 2: Pegar este método dentro de la clase AppController:
// ══════════════════════════════════════════════════════════════════════

  // ── msa-{ms_name_slug} ──────────────────────────────────────────────────────

  @{decorator}('{route_path.strip("/")}')
  {handler_name}(@Query() query: unknown,{body_param}
  @Param() params: unknown) {{
    return this.appService.{handler_name}({{
      query,{body_arg}
      params,
    }});
  }}
"""


def _build_gateway_service_patch(
    ms_name_slug: str,
    http_method: str,
    route_path: str,
    handler_name: str,
    port: int,
) -> str:
    hm = http_method.upper()
    include_body = hm in {"POST", "PUT"}

    metodo_axios = {"GET": "get", "POST": "post", "PUT": "put", "DELETE": "delete"}.get(hm, "get")

    env_var = f"MS_{ms_name_slug.upper().replace('-', '_')}_URL"
    ruta_limpia = route_path.strip("/")

    if include_body:
        firma = f"async {handler_name}(input: {{ query: unknown; body: unknown; params: unknown }})"
        llamada = f"      const {{ data }} = await axios.{metodo_axios}(`${{url}}/{ruta_limpia}`, input.body);"
    else:
        firma = f"async {handler_name}(input: {{ query: unknown; params: unknown }})"
        llamada = f"      const {{ data }} = await axios.{metodo_axios}(`${{url}}/{ruta_limpia}`);"

    return f"""// ══════════════════════════════════════════════════════════════════════
// PARCHE GATEWAY — msa-{ms_name_slug}
// Agregar este bloque en: mdl-billetera/src/app.service.ts
//
// PASO 1: Agregar la constante de URL al inicio del archivo (fuera de la clase):
//
//   const {env_var} =
//     process.env.{env_var} || 'http://msa-{ms_name_slug}:{port}';
//
// PASO 2: Pegar este método dentro de la clase AppService:
// ══════════════════════════════════════════════════════════════════════

  // ── msa-{ms_name_slug} ──────────────────────────────────────────────────────

  {firma}: Promise<unknown> {{
    const url = process.env.{env_var} || 'http://msa-{ms_name_slug}:{port}';
    try {{
{llamada}
      return data;
    }} catch (err) {{
      this.logger.error('Error contactando msa-{ms_name_slug}', err.message);
      return {{ error: 'Microservicio no disponible' }};
    }}
  }}
"""


def _build_docker_compose_patch(ms_name_slug: str, port: int) -> str:
    env_var = f"MS_{ms_name_slug.upper().replace('-', '_')}_URL"
    return f"""# ══════════════════════════════════════════════════════════════════════
# PARCHE DOCKER COMPOSE — msa-{ms_name_slug}
# Agregar este bloque en: docker-compose.yml bajo la sección "services:"
#
# Además, agregar la variable de entorno al servicio mdl-billetera:
#   {env_var}: http://msa-{ms_name_slug}:{port}
# ══════════════════════════════════════════════════════════════════════

  msa-{ms_name_slug}:
    build:
      context: ./msa-{ms_name_slug}
    container_name: msa-{ms_name_slug}
    restart: unless-stopped
    environment:
      DB_HOST: mysql
      DB_PORT: ${{DB_PORT:-3306}}
      DB_USER: ${{DB_USER:-root}}
      DB_PASSWORD: ${{DB_PASSWORD:-secret}}
      DB_NAME: ${{DB_NAME:-billetera}}
      PORT: {port}
    ports:
      - "{port}:{port}"
    depends_on:
      mysql:
        condition: service_healthy
"""


# ─────────────────────────────────────────────────────────────────────────────
# Generador de instrucciones en español
# ─────────────────────────────────────────────────────────────────────────────

def _build_instrucciones(
    ms_name_slug: str,
    entity_snake: str,
    http_method: str,
    route_path: str,
    handler_name: str,
    port: int,
    es_nuevo: bool,
    campos: list[dict],
    metodos_php: list[str],
    akisi_repo_root: str | None,
    flujo: str,
    use_case_slug: str,
) -> str:
    repo_path = akisi_repo_root or "<ruta_repo_nestjs>"

    if flujo == "A":
        estructura = f"""      ├── controllers/
      │   └── {entity_snake}.controller.ts
      ├── use-cases/
      │   └── {use_case_slug}/
      │       └── {use_case_slug}.use-case.ts"""
    else:
        estructura = f"""      ├── {entity_snake}.controller.ts
      ├── {entity_snake}.service.ts"""

    pasos_ms = ""
    if es_nuevo:
        pasos_ms = f"""
## PASO 1 — Copiar el nuevo microservicio al repositorio NestJS

Copiar la carpeta completa:

  ORIGEN : (esta carpeta)  msa-{ms_name_slug}/
  DESTINO: {repo_path}/apps/msa-{ms_name_slug}/

Verificar que la estructura quede así:
  {repo_path}/apps/
  └── msa-{ms_name_slug}/
      ├── Dockerfile
      ├── package.json
      ├── tsconfig.json
      └── src/
{estructura}
          ├── {entity_snake}.model.ts
          ├── app.module.ts
          └── main.ts

## PASO 2 — Instalar dependencias del nuevo microservicio

  cd {repo_path}/apps/msa-{ms_name_slug}
  npm install

## PASO 3 — Actualizar el docker-compose.yml

Abrir: {repo_path}/docker-compose.yml
Agregar el bloque del archivo: docker-compose.patch.yml

"""
    else:
        pasos_ms = f"""
## PASO 1 — Integrar archivos al microservicio existente

Flujo {flujo} — estructura generada:
{estructura}

Copiar los archivos generados a las rutas correspondientes en:
  {repo_path}/apps/msa-{ms_name_slug}/src/

Si los directorios no existen, crearlos primero.

"""

    campos_revisar = ""
    if campos:
        lista = "\n".join([f"  - {c['name']} ({c['sequelize_type']}) → {c['comment']}" for c in campos])
        campos_revisar = f"""
## REVISIÓN DEL MODELO — Campos generados desde PHP

Los siguientes campos fueron detectados automáticamente.
Revisar tipos y restricciones. Si el modelo ya existe en @akisi/sequelize-models,
eliminar el archivo .model.ts generado e importar desde el paquete compartido.

{lista}

"""

    metodos_revisar = ""
    if metodos_php:
        lista = "\n".join([f"  - {m}" for m in metodos_php])
        metodos_revisar = f"""
## REVISIÓN — Llamadas PHP detectadas

Estos métodos del modelo PHP deben implementarse en el use-case/service:

{lista}

"""

    paso_gateway = "4" if es_nuevo else "2"
    paso_verify = "5" if es_nuevo else "3"
    paso_integration = "6" if es_nuevo else "4"

    return f"""# Instrucciones de migración
# Endpoint   : {http_method} {route_path}
# MSA destino: msa-{ms_name_slug} (puerto {port})
# Flujo      : {flujo} ({'controller → use-case' if flujo == 'A' else 'controller → service → use-cases'})
# Generado automáticamente por la herramienta de migración PHP → NestJS
# ──────────────────────────────────────────────────────────────────────
{pasos_ms}
## PASO {paso_gateway} — Actualizar el gateway (mdl-billetera)

Abrir: {repo_path}/apps/mdl-billetera/src/app.controller.ts
→ Agregar el contenido del archivo: gateway-changes/app.controller.patch.ts

Abrir: {repo_path}/apps/mdl-billetera/src/app.service.ts
→ Agregar el contenido del archivo: gateway-changes/app.service.patch.ts

## PASO {paso_verify} — Verificar que todo levanta correctamente

Desde la raíz del repo NestJS:

  docker-compose up --build msa-{ms_name_slug}

Probar el endpoint:

  curl -X {http_method} http://localhost:{port}/{route_path.strip("/")}

## PASO {paso_integration} — Verificar integración con el gateway

  docker-compose up --build mdl-billetera

  curl -X {http_method} http://localhost:3000/{route_path.strip("/")}
{campos_revisar}{metodos_revisar}
## ARCHIVOS GENERADOS EN ESTE OUTPUT

  msa-{ms_name_slug}/                        ← {"Microservicio completo" if es_nuevo else "Archivos a integrar"}
  gateway-changes/
    app.controller.patch.ts                  ← Fragmento para mdl-billetera controller
    app.service.patch.ts                     ← Fragmento para mdl-billetera service
  {"docker-compose.patch.yml                    ← Bloque para agregar al compose" if es_nuevo else ""}
  report.md                                  ← Análisis técnico del endpoint
  changes.md                                 ← Mapeo PHP → Node
  instrucciones.md                           ← Este archivo

──────────────────────────────────────────────────────────────────────
Cualquier duda consultar con el líder técnico antes de hacer merge.
──────────────────────────────────────────────────────────────────────
"""


# ─────────────────────────────────────────────────────────────────────────────
# Función principal
# ─────────────────────────────────────────────────────────────────────────────

def generate_akisi_scaffold(
    out_base_dir: Path,
    http_method: str,
    route_path: str,
    ms_name: str,
    handler_name: str,
    port: int,
    es_nuevo: bool,
    flujo: str = "A",
    analysis_data: dict | None = None,
    akisi_repo_root: str | None = None,
) -> AkisiScaffoldPaths:
    """
    Genera el output de migración completo siguiendo el patrón akisi_backend_nestjs.

    Parámetros:
      out_base_dir   : carpeta base del output (ej. out/resolved/v2/<ekey>)
      http_method    : GET | POST | PUT | DELETE
      route_path     : ruta del endpoint (ej. /customer/customer_by_phone)
      ms_name        : nombre del microservicio sin prefijo (ej. customer)
      handler_name   : nombre del método PHP migrado (ej. customerByPhone)
      port           : puerto asignado al microservicio
      es_nuevo       : True = generar microservicio completo, False = solo archivos del endpoint
      flujo          : "A" = controller→use-case | "B" = controller→service→use-cases
      analysis_data  : dict del analysis.json generado por el extractor PHP
      akisi_repo_root: ruta al repo NestJS destino (para instrucciones)
    """
    flujo = flujo.upper()
    if flujo not in ("A", "B"):
        flujo = "A"

    ms_slug = _slug(ms_name)
    entity_snake = _snake(ms_name)
    entity_class = pascal_case(ms_slug)
    table_name = entity_snake + "s"

    use_case_slug = _handler_slug(handler_name)
    use_case_class = pascal_case(use_case_slug.replace("-", "_")) + "UseCase"

    ms_dir = out_base_dir / f"msa-{ms_slug}"
    src_dir = ms_dir / "src"
    gateway_dir = out_base_dir / "gateway-changes"

    ensure_dir(src_dir)
    ensure_dir(gateway_dir)

    campos = _detectar_campos_modelo(analysis_data)
    metodos_php = _detectar_metodos_servicio(analysis_data)
    codigos_resp, mensajes_resp = _detectar_responses(analysis_data)

    # ── Archivos del microservicio ────────────────────────────────────────────
    model_file = src_dir / f"{entity_snake}.model.ts"
    write_text(model_file, _build_model(entity_class, entity_snake, campos, table_name))

    service_file: Path | None = None
    use_case_file: Path | None = None
    controller_file: Path

    if flujo == "A":
        # Flujo A: controllers/ + use-cases/<handler>/
        controllers_dir = src_dir / "controllers"
        use_cases_dir = src_dir / "use-cases" / use_case_slug
        ensure_dir(controllers_dir)
        ensure_dir(use_cases_dir)

        controller_file = controllers_dir / f"{entity_snake}.controller.ts"
        use_case_file = use_cases_dir / f"{use_case_slug}.use-case.ts"

        write_text(controller_file, _build_controller_flujo_a(
            entity_class, entity_snake, ms_slug, http_method, route_path,
            handler_name, use_case_class, use_case_slug,
        ))
        write_text(use_case_file, _build_use_case(
            entity_class, entity_snake, ms_slug, http_method, handler_name,
            use_case_class, metodos_php, codigos_resp, mensajes_resp, analysis_data,
        ))
    else:
        # Flujo B: archivos planos en src/
        controller_file = src_dir / f"{entity_snake}.controller.ts"
        service_file = src_dir / f"{entity_snake}.service.ts"

        write_text(controller_file, _build_controller_flujo_b(
            entity_class, entity_snake, ms_slug, http_method, route_path, handler_name,
        ))
        write_text(service_file, _build_service(
            entity_class, entity_snake, ms_slug, http_method, handler_name,
            metodos_php, codigos_resp, mensajes_resp, analysis_data,
        ))

    module_file = src_dir / "app.module.ts"
    main_file = src_dir / "main.ts"

    write_text(module_file, _build_app_module(
        entity_class, entity_snake, ms_slug, flujo,
        use_case_class=use_case_class,
        use_case_slug=use_case_slug,
    ))
    write_text(main_file, _build_main(ms_slug, port))

    dockerfile = ms_dir / "Dockerfile"
    package_json = ms_dir / "package.json"
    tsconfig_json = ms_dir / "tsconfig.json"

    if es_nuevo:
        write_text(dockerfile, _build_dockerfile(ms_slug, port))
        write_text(package_json, _build_package_json(ms_slug))
        write_text(tsconfig_json, _build_tsconfig())

    # ── Parches del gateway ───────────────────────────────────────────────────
    gateway_controller_patch = gateway_dir / "app.controller.patch.ts"
    gateway_service_patch = gateway_dir / "app.service.patch.ts"

    write_text(gateway_controller_patch, _build_gateway_controller_patch(
        ms_slug, entity_snake, http_method, route_path, handler_name, port,
    ))
    write_text(gateway_service_patch, _build_gateway_service_patch(
        ms_slug, http_method, route_path, handler_name, port,
    ))

    docker_compose_patch = None
    if es_nuevo:
        docker_compose_patch = out_base_dir / "docker-compose.patch.yml"
        write_text(docker_compose_patch, _build_docker_compose_patch(ms_slug, port))

    instrucciones_file = out_base_dir / "instrucciones.md"
    write_text(instrucciones_file, _build_instrucciones(
        ms_slug, entity_snake, http_method, route_path, handler_name, port,
        es_nuevo, campos, metodos_php, akisi_repo_root, flujo, use_case_slug,
    ))

    return AkisiScaffoldPaths(
        ms_dir=ms_dir,
        controller_file=controller_file,
        service_file=service_file,
        use_case_file=use_case_file,
        model_file=model_file,
        module_file=module_file,
        main_file=main_file,
        dockerfile=dockerfile,
        package_json=package_json,
        tsconfig_json=tsconfig_json,
        gateway_controller_patch=gateway_controller_patch,
        gateway_service_patch=gateway_service_patch,
        docker_compose_patch=docker_compose_patch,
        instrucciones_file=instrucciones_file,
    )

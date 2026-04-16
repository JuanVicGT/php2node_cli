"""
scaffold_akisi.py
=================
Genera el output de migración siguiendo el patrón del repositorio akisi_backend_nestjs.

Patrón de estructura por microservicio:
  msa-<name>/
  ├── Dockerfile
  ├── package.json
  ├── tsconfig.json
  └── src/
      ├── main.ts
      ├── app.module.ts
      ├── <entity>.controller.ts
      ├── <entity>.service.ts
      └── <entity>.model.ts

El gateway (mdl-billetera) recibe archivos de parche con las rutas y llamadas
axios que el dev debe agregar manualmente.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .utils import ensure_dir, write_text, pascal_case, safe_slug


# ─────────────────────────────────────────────────────────────────────────────
# Dataclasses de resultado
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AkisiScaffoldPaths:
    ms_dir: Path
    controller_file: Path
    service_file: Path
    model_file: Path
    module_file: Path
    main_file: Path
    dockerfile: Path
    package_json: Path
    tsconfig_json: Path
    gateway_controller_patch: Path
    gateway_service_patch: Path
    docker_compose_patch: Path | None   # Solo si es microservicio nuevo
    instrucciones_file: Path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────

def _slug(name: str) -> str:
    """Convierte un nombre a slug con guiones. Ej: bank-account"""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "servicio"


def _snake(name: str) -> str:
    """Convierte a snake_case. Ej: bank_account"""
    return _slug(name).replace("-", "_")


def _detectar_campos_modelo(analysis_data: dict | None) -> list[dict]:
    """
    Extrae campos candidatos para el modelo Sequelize desde analysis.json.
    Retorna lista de dicts con: name, ts_type, sequelize_type, nullable, comment.
    """
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

    # Deduplicar manteniendo orden
    vistos: set[str] = set()
    unicos: list[str] = []
    for c in todos:
        if c not in vistos:
            vistos.add(c)
            unicos.append(c)

    # Heurística de tipo por nombre de campo
    campos: list[dict] = []
    for nombre in unicos:
        campo = _inferir_tipo_campo(nombre)
        campos.append(campo)

    return campos


def _inferir_tipo_campo(nombre: str) -> dict:
    """
    Infiere el tipo Sequelize y TypeScript basado en el nombre del campo.
    Heurística simple — el dev debe revisar y ajustar.
    """
    n = nombre.lower()

    if any(k in n for k in ("monto", "amount", "precio", "price", "balance", "total", "saldo")):
        return {
            "name": nombre,
            "ts_type": "number",
            "sequelize_type": "DataType.DECIMAL(12, 2)",
            "nullable": True,
            "comment": "TODO: verificar precisión decimal",
        }
    if any(k in n for k in ("fecha", "date", "hora", "time", "created", "updated")):
        return {
            "name": nombre,
            "ts_type": "Date",
            "sequelize_type": "DataType.DATE",
            "nullable": True,
            "comment": "TODO: verificar formato de fecha",
        }
    if any(k in n for k in ("_id", "id_", "codigo", "code", "numero", "number", "count", "cantidad", "qty")):
        return {
            "name": nombre,
            "ts_type": "number",
            "sequelize_type": "DataType.INTEGER",
            "nullable": True,
            "comment": "TODO: verificar si es FK o PK",
        }
    if any(k in n for k in ("activo", "active", "estado", "status", "habilitado", "enabled")):
        return {
            "name": nombre,
            "ts_type": "string",
            "sequelize_type": "DataType.STRING(20)",
            "nullable": True,
            "comment": "TODO: considerar ENUM si los valores son fijos",
        }
    if any(k in n for k in ("descripcion", "description", "detalle", "detail", "nota", "note", "comentario")):
        return {
            "name": nombre,
            "ts_type": "string",
            "sequelize_type": "DataType.TEXT",
            "nullable": True,
            "comment": "TODO: verificar longitud máxima",
        }
    # Default: string
    return {
        "name": nombre,
        "ts_type": "string",
        "sequelize_type": "DataType.STRING(255)",
        "nullable": True,
        "comment": "TODO: ajustar tipo y longitud",
    }


def _detectar_metodos_servicio(analysis_data: dict | None) -> list[str]:
    """Extrae los nombres de métodos del modelo PHP para usarlos como guía en el servicio."""
    if not analysis_data:
        return []
    calls = analysis_data.get("model_calls", []) or []
    metodos: list[str] = []
    for call in calls:
        # Formato esperado: "ModelName->method_name" o "model_name->method_name"
        if "->" in str(call):
            metodo = str(call).split("->")[-1].strip()
            if metodo and metodo not in metodos:
                metodos.append(metodo)
    return metodos


def _detectar_responses(analysis_data: dict | None) -> tuple[list[str], list[str]]:
    """Retorna (codigos_rest, mensajes) detectados en el PHP."""
    if not analysis_data:
        return [], []
    responses = analysis_data.get("responses", {}) or {}
    codigos = [str(c) for c in (responses.get("rest_codes", []) or []) if c]
    mensajes = [str(m) for m in (responses.get("messages", []) or []) if m]
    return codigos, mensajes


# ─────────────────────────────────────────────────────────────────────────────
# Generadores de archivos TypeScript
# ─────────────────────────────────────────────────────────────────────────────

def _build_model(
    entity_class: str,
    entity_snake: str,
    campos: list[dict],
    table_name: str,
) -> str:
    """Genera el modelo Sequelize con campos detectados desde PHP."""
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
 * Revisar y ajustar tipos, longitudes y restricciones antes de usar en producción.
 * Los campos marcados con TODO requieren validación manual.
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
    """Genera el servicio NestJS con guía de migración desde PHP."""
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

    guia = "\n".join(comentarios_migracion)

    return f"""import {{ Injectable }} from '@nestjs/common';
import {{ InjectModel }} from '@nestjs/sequelize';
import {{ {entity_class} }} from '../{entity_snake}.model';

/**
 * Servicio: {entity_class}Service
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


def _build_controller(
    entity_class: str,
    entity_snake: str,
    ms_name_slug: str,
    http_method: str,
    route_path: str,
    handler_name: str,
) -> str:
    """Genera el controller NestJS con el decorador HTTP correcto."""
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
 * Microservicio: msa-{ms_name_slug}
 *
 * Generado automáticamente desde la herramienta de migración PHP → NestJS.
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
    db_name: str = "billetera",
) -> str:
    """Genera el app.module.ts del microservicio con Sequelize configurado."""
    return f"""import {{ Module }} from '@nestjs/common';
import {{ SequelizeModule }} from '@nestjs/sequelize';
import {{ {entity_class} }} from './{entity_snake}.model';
import {{ {entity_class}Controller }} from './{entity_snake}.controller';
import {{ {entity_class}Service }} from './{entity_snake}.service';

/**
 * Módulo raíz del microservicio msa-{ms_name_slug}
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
      // IMPORTANTE: en producción cambiar a false y usar migraciones SQL
      synchronize: process.env.NODE_ENV !== 'production',
    }}),
    SequelizeModule.forFeature([{entity_class}]),
  ],
  controllers: [{entity_class}Controller],
  providers: [{entity_class}Service],
}})
export class AppModule {{}}
"""


def _build_main(ms_name_slug: str, port: int) -> str:
    """Genera el main.ts del microservicio."""
    return f"""import 'reflect-metadata';
import {{ NestFactory }} from '@nestjs/core';
import {{ AppModule }} from './app.module';

/**
 * Bootstrap del microservicio msa-{ms_name_slug}
 * Puerto: {port}
 */
async function bootstrap() {{
  const app = await NestFactory.create(AppModule);
  await app.listen(process.env.PORT ?? {port}, '0.0.0.0');
  console.log(`msa-{ms_name_slug} corriendo en el puerto: ${{process.env.PORT ?? {port}}}`);
}}
bootstrap();
"""


def _build_package_json(ms_name_slug: str) -> str:
    """Genera el package.json del microservicio."""
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
    """Genera el Dockerfile del microservicio."""
    return f"""# Dockerfile — msa-{ms_name_slug}
# Generado automáticamente por la herramienta de migración PHP → NestJS

FROM node:20-alpine

WORKDIR /app

COPY package.json .
RUN npm install

COPY . .
RUN npm run build

EXPOSE {port}

CMD ["npm", "run", "start"]
"""


def _build_tsconfig() -> str:
    """Genera el tsconfig.json estándar del microservicio."""
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
    """Genera el bloque de código a agregar en app.controller.ts del gateway."""
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
    """Genera el bloque de código a agregar en app.service.ts del gateway."""
    hm = http_method.upper()
    include_body = hm in {"POST", "PUT"}

    metodo_axios = {
        "GET": "get",
        "POST": "post",
        "PUT": "put",
        "DELETE": "delete",
    }.get(hm, "get")

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
    """Genera el bloque de servicio a agregar en docker-compose.yml."""
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
) -> str:
    repo_path = akisi_repo_root or "<ruta_repo_nestjs>"

    pasos_ms = ""
    if es_nuevo:
        pasos_ms = f"""
## PASO 1 — Copiar el nuevo microservicio al repositorio NestJS

Copiar la carpeta completa:

  ORIGEN : (esta carpeta)  msa-{ms_name_slug}/
  DESTINO: {repo_path}/msa-{ms_name_slug}/

Verificar que la estructura quede así:
  {repo_path}/
  └── msa-{ms_name_slug}/
      ├── Dockerfile
      ├── package.json
      ├── tsconfig.json
      └── src/
          ├── main.ts
          ├── app.module.ts
          ├── {entity_snake}.controller.ts
          ├── {entity_snake}.service.ts
          └── {entity_snake}.model.ts

## PASO 2 — Instalar dependencias del nuevo microservicio

Abrir terminal en la carpeta del microservicio:

  cd {repo_path}/msa-{ms_name_slug}
  npm install

## PASO 3 — Actualizar el docker-compose.yml

Abrir: {repo_path}/docker-compose.yml

Agregar el bloque del archivo: docker-compose.patch.yml
(ver instrucciones dentro del archivo .patch.yml)

También agregar la variable de entorno al servicio mdl-billetera:
  MS_{ms_name_slug.upper().replace("-", "_")}_URL: http://msa-{ms_name_slug}:{port}

"""
    else:
        pasos_ms = f"""
## PASO 1 — Agregar archivos al microservicio existente

Los archivos en msa-{ms_name_slug}/src/ son los métodos nuevos a integrar.

  ORIGEN : (esta carpeta)  msa-{ms_name_slug}/src/{entity_snake}.controller.ts
  DESTINO: {repo_path}/msa-{ms_name_slug}/src/{entity_snake}.controller.ts

Si el controller ya existe, agregar solo el método nuevo (ver archivo .patch).
Si el modelo aún no existe, copiar también {entity_snake}.model.ts

"""

    campos_revisar = ""
    if campos:
        lista = "\n".join([f"  - {c['name']} ({c['sequelize_type']}) → {c['comment']}" for c in campos])
        campos_revisar = f"""
## REVISIÓN DEL MODELO — Campos generados desde PHP

Los siguientes campos fueron detectados automáticamente.
Revisar tipos y restricciones antes de continuar:

{lista}

"""

    metodos_revisar = ""
    if metodos_php:
        lista = "\n".join([f"  - {m}" for m in metodos_php])
        metodos_revisar = f"""
## REVISIÓN DEL SERVICIO — Llamadas PHP detectadas

Estos métodos del modelo PHP fueron detectados y deben implementarse en el servicio:

{lista}

Buscar en el archivo {entity_snake}.service.ts los comentarios "TODO" para cada uno.

"""

    return f"""# Instrucciones de migración
# Endpoint: {http_method} {route_path}
# Microservicio: msa-{ms_name_slug} (puerto {port})
# Generado automáticamente por la herramienta de migración PHP → NestJS
# ──────────────────────────────────────────────────────────────────────
{pasos_ms}
## PASO {"4" if es_nuevo else "2"} — Actualizar el gateway (mdl-billetera)

Abrir: {repo_path}/mdl-billetera/src/app.controller.ts
→ Agregar el contenido del archivo: gateway-changes/app.controller.patch.ts

Abrir: {repo_path}/mdl-billetera/src/app.service.ts
→ Agregar el contenido del archivo: gateway-changes/app.service.patch.ts

## PASO {"5" if es_nuevo else "3"} — Verificar que todo levanta correctamente

Desde la raíz del repo NestJS:

  docker-compose up --build msa-{ms_name_slug}

Si el servicio levanta sin errores, probar el endpoint:

  curl -X {http_method} http://localhost:{port}/{route_path.strip("/")}

{"## PASO 6 — Verificar integración con el gateway" if es_nuevo else "## PASO 4 — Verificar integración con el gateway"}

  docker-compose up --build mdl-billetera

Probar desde el gateway (puerto 3000):

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
    analysis_data: dict | None = None,
    akisi_repo_root: str | None = None,
) -> AkisiScaffoldPaths:
    """
    Genera el output de migración completo siguiendo el patrón akisi_backend_nestjs.

    Parámetros:
      out_base_dir   : carpeta base del output (ej. out/resolved/v1/<ekey>)
      http_method    : GET | POST | PUT | DELETE
      route_path     : ruta del endpoint (ej. /v1/bank_account/dacustomer_bank)
      ms_name        : nombre del microservicio sin prefijo (ej. bank-account)
      handler_name   : nombre del método PHP migrado (ej. dacustomer_bank)
      port           : puerto asignado al microservicio
      es_nuevo       : True = generar microservicio completo, False = solo parche
      analysis_data  : dict del analysis.json generado por el extractor PHP
      akisi_repo_root: ruta al repo NestJS destino (para instrucciones)
    """
    ms_slug = _slug(ms_name)
    entity_snake = _snake(ms_name)
    entity_class = pascal_case(ms_slug)
    table_name = entity_snake + "s"

    ms_dir = out_base_dir / f"msa-{ms_slug}"
    src_dir = ms_dir / "src"
    gateway_dir = out_base_dir / "gateway-changes"

    ensure_dir(src_dir)
    ensure_dir(gateway_dir)

    # Analizar datos PHP
    campos = _detectar_campos_modelo(analysis_data)
    metodos_php = _detectar_metodos_servicio(analysis_data)
    codigos_resp, mensajes_resp = _detectar_responses(analysis_data)

    # ── Archivos del microservicio ────────────────────────────────────────────
    model_file = src_dir / f"{entity_snake}.model.ts"
    controller_file = src_dir / f"{entity_snake}.controller.ts"
    service_file = src_dir / f"{entity_snake}.service.ts"
    module_file = src_dir / "app.module.ts"
    main_file = src_dir / "main.ts"
    dockerfile = ms_dir / "Dockerfile"
    package_json = ms_dir / "package.json"
    tsconfig_json = ms_dir / "tsconfig.json"

    write_text(model_file, _build_model(entity_class, entity_snake, campos, table_name))
    write_text(controller_file, _build_controller(entity_class, entity_snake, ms_slug, http_method, route_path, handler_name))
    write_text(service_file, _build_service(entity_class, entity_snake, ms_slug, http_method, handler_name, metodos_php, codigos_resp, mensajes_resp, analysis_data))
    write_text(module_file, _build_app_module(entity_class, entity_snake, ms_slug))
    write_text(main_file, _build_main(ms_slug, port))

    if es_nuevo:
        write_text(dockerfile, _build_dockerfile(ms_slug, port))
        write_text(package_json, _build_package_json(ms_slug))
        write_text(tsconfig_json, _build_tsconfig())

    # ── Parches del gateway ───────────────────────────────────────────────────
    gateway_controller_patch = gateway_dir / "app.controller.patch.ts"
    gateway_service_patch = gateway_dir / "app.service.patch.ts"

    write_text(gateway_controller_patch, _build_gateway_controller_patch(ms_slug, entity_snake, http_method, route_path, handler_name, port))
    write_text(gateway_service_patch, _build_gateway_service_patch(ms_slug, http_method, route_path, handler_name, port))

    # ── Docker compose patch (solo si es nuevo) ───────────────────────────────
    docker_compose_patch = None
    if es_nuevo:
        docker_compose_patch = out_base_dir / "docker-compose.patch.yml"
        write_text(docker_compose_patch, _build_docker_compose_patch(ms_slug, port))

    # ── Instrucciones en español ──────────────────────────────────────────────
    instrucciones_file = out_base_dir / "instrucciones.md"
    write_text(
        instrucciones_file,
        _build_instrucciones(ms_slug, entity_snake, http_method, route_path, handler_name, port, es_nuevo, campos, metodos_php, akisi_repo_root),
    )

    return AkisiScaffoldPaths(
        ms_dir=ms_dir,
        controller_file=controller_file,
        service_file=service_file,
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

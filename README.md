# Xib — Herramienta de Migración PHP → NestJS

Herramienta CLI para migrar endpoints de CodeIgniter (PHP) al patrón de microservicios de `akisi_backend_nestjs` (NestJS + Sequelize + MySQL).

Por cada endpoint analizado genera automáticamente:
- El microservicio NestJS completo o los archivos a integrar en uno existente
- El modelo Sequelize con los campos detectados desde el PHP
- Los parches para el gateway (`mdl-billetera`)
- El bloque para el `docker-compose.yml`
- Instrucciones en español paso a paso para el dev

---

## Requisitos

- Python 3.10 o superior
- Git Bash (Windows) o terminal bash (Mac/Linux)
- Acceso local al repositorio PHP/CodeIgniter a migrar
- Acceso local al repositorio NestJS destino (`akisi_backend_nestjs`)
- Inventario de endpoints en formato Excel (`.xlsx`)

---

## Instalación — primera vez

### Paso 1 — Clonar la herramienta

```bash
git clone <url-del-repo>
cd php2node_cli
```

### Paso 2 — Crear el entorno virtual e instalar dependencias

```bash
python -m venv .venv

# Activar el entorno (Windows Git Bash)
source .venv/Scripts/activate

# Activar el entorno (Mac/Linux)
source .venv/bin/activate

# Instalar
pip install -e .
```

### Paso 3 — Configurar rutas locales

Ejecuta el asistente de configuración. Crea el archivo `.env` con tus rutas locales:

```bash
bash setup.sh
```

El asistente te pide:
1. Ruta al repositorio PHP local
2. Ruta al repositorio NestJS destino
3. Ruta al inventario Excel v1
4. Ruta al inventario Excel v2
5. Nombre de la hoja en el Excel (default: `EndPoints`)
6. Carpeta de salida (default: `./out`)

### Paso 4 — Verificar instalación

```bash
php2node -h
```

---

## Uso diario

Una vez instalado y configurado, el flujo normal es:

```bash
# Activar entorno virtual (si no está activo)
source .venv/Scripts/activate

# Lanzar la interfaz interactiva
bash xib.sh
```

La herramienta te guía paso a paso:

```
[1/6] Endpoint a migrar        → Ej: bank_account/dacustomer_bank
[2/6] Método HTTP              → GET | POST | PUT | DELETE
[3/6] Versión del inventario   → v1 | v2 | Detectar automáticamente
[4/6] ¿Microservicio nuevo?    → Nuevo | Ya existe
[5/6] Nombre del microservicio → Ej: bank-account  (la herramienta agrega ms-)
[6/6] Puerto                   → Detectado automáticamente o ingresa uno
```

Al final muestra un resumen y pide confirmación antes de ejecutar.

---

## Qué genera por cada endpoint

### Caso A — Microservicio nuevo

```
out/resolved/<version>/<endpoint_key>/
├── ms-<nombre>/
│   ├── Dockerfile
│   ├── package.json
│   ├── tsconfig.json
│   └── src/
│       ├── main.ts
│       ├── app.module.ts
│       ├── <entidad>.controller.ts
│       ├── <entidad>.service.ts
│       └── <entidad>.model.ts        ← modelo Sequelize con campos detectados desde PHP
├── gateway-changes/
│   ├── app.controller.patch.ts       ← ruta nueva para mdl-billetera
│   └── app.service.patch.ts          ← llamada axios para mdl-billetera
├── docker-compose.patch.yml          ← bloque del nuevo servicio
├── instrucciones.md                  ← pasos en español para el dev
├── report.md                         ← análisis técnico del endpoint
└── changes.md                        ← mapeo PHP → Node
```

### Caso B — Microservicio existente

```
out/resolved/<version>/<endpoint_key>/
├── ms-<nombre>/
│   └── src/
│       ├── <entidad>.controller.ts   ← método nuevo a integrar
│       ├── <entidad>.service.ts      ← método nuevo a integrar
│       └── <entidad>.model.ts
├── gateway-changes/
│   ├── app.controller.patch.ts
│   └── app.service.patch.ts
├── instrucciones.md
├── report.md
└── changes.md
```

---

## Variables de entorno (.env)

| Variable | Descripción | Obligatoria |
|---|---|---|
| `PHP2NODE_REPO_ROOT` | Ruta al repo PHP/CodeIgniter local | Sí |
| `AKISI_REPO_ROOT` | Ruta al repo NestJS destino | Recomendada |
| `PHP2NODE_INVENTORY_V1_XLSX` | Ruta al Excel de inventario v1 | Sí (si usas v1) |
| `PHP2NODE_INVENTORY_V2_XLSX` | Ruta al Excel de inventario v2 | Sí (si usas v2) |
| `PHP2NODE_SHEET` | Nombre de la hoja en el Excel | No (default: `EndPoints`) |
| `PHP2NODE_OUT` | Carpeta de salida | No (default: `./out`) |
| `PHP2NODE_APP` | Scope de búsqueda en PHP (`api`/`portal`/`auto`) | No (default: `auto`) |

Usa `example.env` como plantilla base.

---

## Uso avanzado — comando directo

También puedes ejecutar sin la interfaz interactiva:

```bash
# Microservicio nuevo
php2node \
  --http-method GET \
  --endpoint-path "bank_account/dacustomer_bank" \
  --version v1 \
  --ms-name bank-account \
  --ms-new \
  --ms-port 3004 \
  --akisi-root "D:/HomeLand/New Reposistory/akisi_backend_nestjs" \
  -v

# Microservicio existente
php2node \
  --http-method POST \
  --endpoint-path "customer/create_customer" \
  --version v1 \
  --ms-name customer \
  -v
```

### Parámetros disponibles

| Parámetro | Descripción | Obligatorio |
|---|---|---|
| `--http-method` | `GET`, `POST`, `PUT`, `DELETE` | Sí |
| `--endpoint-path` | Ruta del endpoint sin barra inicial | Sí |
| `--ms-name` | Nombre del microservicio sin prefijo `ms-` | Recomendado |
| `--ms-new` | Flag: genera microservicio completo nuevo | No |
| `--ms-port` | Puerto del microservicio nuevo | No (se detecta automáticamente) |
| `--version` | `v1` o `v2`. Si se omite, se infiere del inventario | No |
| `--akisi-root` | Ruta al repo NestJS (también via `AKISI_REPO_ROOT`) | No |
| `--inventory-xlsx` | Ruta al Excel (también via `.env`) | No |
| `--sheet` | Hoja del Excel | No (default: `EndPoints`) |
| `--out` | Carpeta de salida | No (default: `./out`) |
| `--app` | Scope PHP: `api`/`portal`/`auto` | No (default: `auto`) |
| `--clean-out` | Limpia la carpeta `out/` antes de ejecutar | No |
| `-v` / `-vv` | Verbosidad del log | No |

---

## Generación del inventario Excel (filtrado por versión)

Si tu inventario base tiene una columna `Version` con valores `v1`/`v2`, puedes generar archivos separados:

```bash
# Generar inventario v1
python filter_v1.py \
  --src "D:/HomeLand/PHP Migration/EndPoints_DISCOVERED.xlsx" \
  --dst "D:/HomeLand/PHP Migration/EndPoints_DISCOVERED_v1.xlsx" \
  --version v1 \
  --sheet "EndPoints"

# Generar inventario v2
python filter_v1.py \
  --src "D:/HomeLand/PHP Migration/EndPoints_DISCOVERED.xlsx" \
  --dst "D:/HomeLand/PHP Migration/EndPoints_DISCOVERED_v2.xlsx" \
  --version v2 \
  --sheet "EndPoints"
```

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'openpyxl'`
```bash
pip install openpyxl
```

### `ModuleNotFoundError: No module named 'dotenv'`
```bash
pip install python-dotenv
```

### `.env no carga las variables`
Verifica que estás ejecutando el comando desde la raíz del proyecto donde está el `.env`:
```bash
python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print(os.getenv('PHP2NODE_REPO_ROOT'))"
```

### `Unresolved: controller file not found`
Causas comunes:
- `PHP2NODE_REPO_ROOT` apunta a una ruta incorrecta
- El nombre del controller en el inventario no coincide con el archivo real
- El scope `--app` está restringiendo la búsqueda

Acciones:
- Revisar `PHP2NODE_REPO_ROOT` en `.env`
- Ejecutar con `-vv` para ver todas las rutas probadas
- Probar con `--app auto`

### `php2node: command not found`
El entorno virtual no está activo. Ejecutar:
```bash
source .venv/Scripts/activate   # Windows Git Bash
source .venv/bin/activate        # Mac/Linux
```

### Rutas con espacios en Windows
Usar comillas dobles en el `.env` y en los argumentos:
```bash
--repo-root "D:/HomeLand/PHP Migration/api-backend"
```

---

## Flujo recomendado para el equipo

1. Clonar este repositorio en tu máquina local
2. Ejecutar `bash setup.sh` (una sola vez)
3. Activar el entorno virtual: `source .venv/Scripts/activate`
4. Ejecutar `bash xib.sh` por cada endpoint a migrar
5. Revisar el output en `out/resolved/`
6. Seguir el `instrucciones.md` generado para integrar al repo NestJS
7. Validar con `docker-compose up --build <ms-nombre>`

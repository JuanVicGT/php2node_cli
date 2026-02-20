# php2node_cli
# php2node_cli

Herramienta CLI para:
1) Consumir un inventario de endpoints (Excel) generado desde CodeIgniter (PHP)
2) Resolver el controller y método PHP real en el repo legacy
3) Extraer el método PHP
4) Generar scaffold de Node.js (Express + TypeScript)
5) Generar documentación por endpoint (report.md, changes.md, analysis.json)

## Qué genera la herramienta

Por cada endpoint resuelto crea una carpeta bajo `out/`:


out/
resolved/
v1/
<endpoint_key>/
php/
controller_path.txt
method.php
analysis.json
node/
controllers/
routes/
services/
types/
report.md
changes.md


## Requisitos

- Python 3.10+ (recomendado)
- pip
- Acceso local al repo PHP que se va a analizar (no se sube al repo de la herramienta)
- Excel de inventario de endpoints (v1 o v2)

Dependencias Python:
- openpyxl
- python-dotenv (opcional, recomendado)

## Instalación local (recomendada)

Desde la carpeta raíz de la herramienta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e .

Si vas a usar el filtro para Excel:

python -m pip install openpyxl

Si vas a usar .env:

python -m pip install python-dotenv

Verifica:

php2node -h
Configuración con .env

Crea un archivo .env en la raíz del repo (usa example.env como base).

Ejemplo (.env)
# Ruta al repo PHP/CodeIgniter a analizar (local)
PHP2NODE_REPO_ROOT="D:\HomeLand\PHP Migration\PHP apibackend\api-backend"

# Inventarios. Puedes cambiar entre v1/v2 con el comando, o cambiar esta variable.
# OJO: si usas 2 inventarios, define ambos y elige con --inventory-xlsx al ejecutar.
PHP2NODE_INVENTORY_XLSX_V1="D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v1.xlsx"
PHP2NODE_INVENTORY_XLSX_V2="D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v2.xlsx"

# Inventario por defecto (si no pasas --inventory-xlsx)
PHP2NODE_INVENTORY_XLSX="D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v1.xlsx"

# Nombre de la hoja
PHP2NODE_SHEET="EndPoints"

# Carpeta de salida (se recomienda dentro del repo de herramienta)
PHP2NODE_OUT=".\out"

# Alcance de búsqueda de controllers: api | portal | auto
PHP2NODE_APP="auto"
Nota importante sobre comillas

En Windows PowerShell es recomendable usar comillas en rutas con espacios.
En .env usa comillas dobles "..." para rutas.

Cómo generar inventario v1/v2 (Excel filtrado)

El inventario base (descubierto) debe contener una columna Version con valores como v1 / v2.

Ejemplos:

Generar v1
python .\filter_v1.py `
  --src "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED.xlsx" `
  --dst "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v1.xlsx" `
  --version v1 `
  --sheet "EndPoints"
Generar v2
python .\filter_v1.py `
  --src "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED.xlsx" `
  --dst "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v2.xlsx" `
  --version v2 `
  --sheet "EndPoints"

Nota: aunque el script se llame filter_v1.py, acepta --version v2.
Si luego quieres, lo renombramos a filter_version.py para que sea más claro.

Ejecución de la herramienta
Comando corto (usando .env)

Usa defaults desde .env (repo-root, sheet, out, app, inventory por defecto).

php2node --clean-out --http-method GET --endpoint-path "bank_account/dacustomer_bank" -v
Ejecutar forzando v1 (y usando inventario v1)
php2node --clean-out `
  --inventory-xlsx "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v1.xlsx" `
  --http-method GET `
  --endpoint-path "bank_account/dacustomer_bank" `
  --version v1 -v
Ejecutar forzando v2 (y usando inventario v2)
php2node --clean-out `
  --inventory-xlsx "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v2.xlsx" `
  --http-method GET `
  --endpoint-path "bank_account/dacustomer_bank" `
  --version v2 -v
Si NO quieres pasar --version

Puedes omitir --version y la herramienta lo infiere desde el inventario:

php2node --clean-out `
  --inventory-xlsx "D:\HomeLand\PHP Migration\EndPoints_DISCOVERED_v2.xlsx" `
  --http-method GET `
  --endpoint-path "bank_account/dacustomer_bank" -v
Qué parámetros son obligatorios

Obligatorios siempre:

--http-method

--endpoint-path

Obligatorios si no están en .env:

--repo-root o PHP2NODE_REPO_ROOT

--inventory-xlsx o PHP2NODE_INVENTORY_XLSX

Opcionales:

--version (si no se pasa, intenta inferir)

--sheet (default EndPoints)

--out (default ./out)

--app (default auto)

--clean-out (limpia out antes de correr)

Troubleshooting rápido
1) ModuleNotFoundError: No module named 'openpyxl'

Instala:

python -m pip install openpyxl
2) .env no carga variables (sale None)

Verifica:

Estás ejecutando el comando desde la raíz del repo donde está .env

Tienes instalado python-dotenv

Instala:

python -m pip install python-dotenv

Prueba:

python -c "import os; from dotenv import load_dotenv; load_dotenv('.env'); print(os.getenv('PHP2NODE_REPO_ROOT'))"
3) Unresolved: controller file not found

Causas comunes:

PHP2NODE_REPO_ROOT apunta a una ruta incorrecta

El inventario tiene Controller que no existe o el nombre no calza con el archivo real

--app está restringiendo la búsqueda (usa auto)

Acciones:

Revisa .env (repo root)

Ejecuta con -vv para más detalle (si tienes verbose 2)

Prueba --app auto

4) PowerShell falla con rutas que tienen espacios

Usa comillas:

--repo-root "D:\HomeLand\PHP Migration\PHP apibackend\api-backend"
Recomendación de flujo para el equipo

Clonar repo herramienta

Crear .venv + pip install -e .

Copiar example.env a .env y ajustar rutas locales

Generar inventario v1 / v2 (si aplica)

Ejecutar por endpoint con php2node ...

Revisar carpeta out/resolved/<vX>/... y usar report.md + changes.md como base de documentación


---

## Ajuste que te recomiendo (pequeño, pero útil)
En tu `cli.py` actual, el `.env` solo soporta `PHP2NODE_INVENTORY_XLSX` como default. Como tú quieres tener **v1 y v2 en el .env**, lo mejor es:

- Mantener:
  - `PHP2NODE_INVENTORY_XLSX_V1`
  - `PHP2NODE_INVENTORY_XLSX_V2`
- Y que el CLI, si pasas `--version v2` pero NO pasas `--inventory-xlsx`, automáticamente use la variable `..._V2` (y lo mismo para v1).

Si quieres, te paso el cambio exacto en `cli.py` para ese comportamiento (es corto y no rompe nada).

¿Quieres que el README diga que el `--inventory-xlsx` se elige automático por versión, o lo dejamos manual como está hoy?
#!/usr/bin/env bash
# setup.sh
# Configuración inicial de la herramienta de migración PHP → NestJS
# Ejecutar una sola vez por desarrollador al clonar el repositorio.
# Uso: bash setup.sh

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Colores para la terminal
# ─────────────────────────────────────────────────────────────────────────────
VERDE="\033[0;32m"
AMARILLO="\033[1;33m"
ROJO="\033[0;31m"
CYAN="\033[0;36m"
RESET="\033[0m"

linea() { echo -e "${CYAN}══════════════════════════════════════════════════════${RESET}"; }
ok()    { echo -e "${VERDE}  ✔  $1${RESET}"; }
warn()  { echo -e "${AMARILLO}  ⚠  $1${RESET}"; }
error() { echo -e "${ROJO}  ✘  $1${RESET}"; }

# ─────────────────────────────────────────────────────────────────────────────
clear
linea
echo -e "${CYAN}   CONFIGURACIÓN INICIAL — Herramienta de Migración PHP → NestJS${RESET}"
linea
echo ""
echo "  Este asistente crea tu archivo .env con las rutas locales de tu máquina."
echo "  Solo necesitas ejecutarlo una vez."
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Verificar si ya existe un .env
# ─────────────────────────────────────────────────────────────────────────────
if [[ -f ".env" ]]; then
    warn ".env ya existe."
    echo ""
    read -rp "  ¿Deseas sobreescribirlo? (s/n): " CONFIRMAR
    if [[ "$CONFIRMAR" != "s" && "$CONFIRMAR" != "S" ]]; then
        echo ""
        echo "  Configuración cancelada. Tu .env actual no fue modificado."
        exit 0
    fi
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# Preguntas de configuración
# ─────────────────────────────────────────────────────────────────────────────
linea
echo -e "${CYAN}  [1/6] Ruta al repositorio PHP/CodeIgniter local${RESET}"
echo "  Ejemplo: D:/HomeLand/PHP Migration/api-backend"
echo ""
read -rp "  > " PHP_REPO_ROOT
echo ""

linea
echo -e "${CYAN}  [2/6] Ruta al repositorio NestJS destino (akisi_backend_nestjs)${RESET}"
echo "  Ejemplo: D:/HomeLand/New Reposistory/akisi_backend_nestjs"
echo ""
read -rp "  > " AKISI_REPO_ROOT
echo ""

linea
echo -e "${CYAN}  [3/6] Ruta al inventario Excel — versión v1${RESET}"
echo "  Ejemplo: D:/HomeLand/PHP Migration/EndPoints_DISCOVERED_v1.xlsx"
echo ""
read -rp "  > " INV_V1
echo ""

linea
echo -e "${CYAN}  [4/6] Ruta al inventario Excel — versión v2${RESET}"
echo "  Ejemplo: D:/HomeLand/PHP Migration/EndPoints_DISCOVERED_v2.xlsx"
echo "  (Deja en blanco si solo usas v1)"
echo ""
read -rp "  > " INV_V2
echo ""

linea
echo -e "${CYAN}  [5/6] Nombre de la hoja en el Excel${RESET}"
echo "  Valor por defecto: EndPoints"
echo ""
read -rp "  > " SHEET_NAME
SHEET_NAME="${SHEET_NAME:-EndPoints}"
echo ""

linea
echo -e "${CYAN}  [6/6] Carpeta de salida del output${RESET}"
echo "  Valor por defecto: ./out"
echo ""
read -rp "  > " OUT_DIR
OUT_DIR="${OUT_DIR:-./out}"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Escribir el archivo .env
# ─────────────────────────────────────────────────────────────────────────────
cat > .env <<EOF
# ── Repositorios ──────────────────────────────────────────────────────────────
# Ruta local al repo PHP/CodeIgniter a migrar
PHP2NODE_REPO_ROOT="${PHP_REPO_ROOT}"

# Ruta local al repo NestJS destino
AKISI_REPO_ROOT="${AKISI_REPO_ROOT}"

# ── Inventarios Excel ─────────────────────────────────────────────────────────
PHP2NODE_INVENTORY_V1_XLSX="${INV_V1}"
PHP2NODE_INVENTORY_V2_XLSX="${INV_V2}"
PHP2NODE_SHEET="${SHEET_NAME}"

# ── Salida ────────────────────────────────────────────────────────────────────
PHP2NODE_OUT="${OUT_DIR}"

# ── Scope de búsqueda en el repo PHP ─────────────────────────────────────────
# Valores posibles: api | portal | auto
PHP2NODE_APP="auto"
EOF

echo ""
linea
ok ".env creado correctamente."
linea
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Verificar entorno Python
# ─────────────────────────────────────────────────────────────────────────────
echo -e "${CYAN}  Verificando entorno Python...${RESET}"
echo ""

PYTHON_OK=false
VENV_OK=false
TOOL_OK=false

# Verificar Python
if command -v python &> /dev/null; then
    PY_VERSION=$(python --version 2>&1)
    ok "Python encontrado: $PY_VERSION"
    PYTHON_OK=true
elif command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1)
    ok "Python encontrado: $PY_VERSION"
    PYTHON_OK=true
else
    error "Python no encontrado en el PATH."
fi

# Verificar virtualenv
if [[ -d ".venv" ]]; then
    ok "Entorno virtual .venv encontrado."
    VENV_OK=true
else
    warn "Entorno virtual .venv no encontrado."
fi

# Verificar que la herramienta está instalada
if command -v php2node &> /dev/null; then
    ok "Herramienta php2node instalada correctamente."
    TOOL_OK=true
else
    warn "Herramienta php2node no instalada aún."
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Instrucciones de instalación si falta algo
# ─────────────────────────────────────────────────────────────────────────────
if [[ "$VENV_OK" == false || "$TOOL_OK" == false ]]; then
    linea
    echo -e "${AMARILLO}  PASOS DE INSTALACIÓN PENDIENTES${RESET}"
    linea
    echo ""

    if [[ "$PYTHON_OK" == false ]]; then
        echo "  Primero instala Python 3.10 o superior desde: https://www.python.org/downloads/"
        echo "  Luego vuelve a ejecutar este script."
        echo ""
    fi

    if [[ "$VENV_OK" == false ]]; then
        echo "  PASO 1 — Crear el entorno virtual:"
        echo ""
        echo "    python -m venv .venv"
        echo ""
    fi

    echo "  PASO 2 — Activar el entorno virtual:"
    echo ""
    echo "    Windows (Git Bash):  source .venv/Scripts/activate"
    echo "    Mac/Linux:           source .venv/bin/activate"
    echo ""

    echo "  PASO 3 — Instalar la herramienta y sus dependencias:"
    echo ""
    echo "    pip install -e ."
    echo ""

    echo "  PASO 4 — Verificar la instalación:"
    echo ""
    echo "    php2node -h"
    echo ""

    linea
    echo ""
    echo "  Una vez completados esos pasos, ejecuta la herramienta con:"
    echo ""
    echo "    bash toolmigration.sh"
    echo ""
else
    linea
    echo ""
    echo "  Todo listo. Puedes comenzar con:"
    echo ""
    echo "    bash toolmigration.sh"
    echo ""
fi

linea

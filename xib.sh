#!/usr/bin/env bash
# xib.sh — Herramienta de migración PHP → NestJS
# "Xib" significa transformación en maya k'iche'
# Uso: bash xib.sh

set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Colores
# ─────────────────────────────────────────────────────────────────────────────
VERDE="\033[0;32m"
AMARILLO="\033[1;33m"
ROJO="\033[0;31m"
CYAN="\033[0;36m"
BLANCO="\033[1;37m"
RESET="\033[0m"

linea()     { echo -e "${CYAN}══════════════════════════════════════════════════════${RESET}"; }
linea_sm()  { echo -e "${CYAN}──────────────────────────────────────────────────────${RESET}"; }
ok()        { echo -e "${VERDE}  ✔  $1${RESET}"; }
warn()      { echo -e "${AMARILLO}  ⚠  $1${RESET}"; }
error_msg() { echo -e "${ROJO}  ✘  $1${RESET}"; }
titulo()    { echo -e "${BLANCO}  $1${RESET}"; }

# ─────────────────────────────────────────────────────────────────────────────
# Verificar .env
# ─────────────────────────────────────────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    echo ""
    error_msg "No se encontró el archivo .env."
    echo ""
    echo "  Ejecuta primero la configuración inicial:"
    echo ""
    echo "    bash setup.sh"
    echo ""
    exit 1
fi

# Cargar variables del .env de forma segura
# Soporta rutas con espacios y valores sin comillas
while IFS= read -r line || [[ -n "$line" ]]; do
    # Saltar comentarios y líneas vacías
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    # Extraer clave y valor con regex (soporta = dentro del valor)
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
        _key="${BASH_REMATCH[1]}"
        _val="${BASH_REMATCH[2]}"
        # Quitar comillas dobles o simples si las tiene
        _val="${_val#\"}" ; _val="${_val%\"}"
        _val="${_val#\'}" ; _val="${_val%\'}"
        export "$_key=$_val"
    fi
done < .env

# ─────────────────────────────────────────────────────────────────────────────
# Verificar que php2node está disponible
# ─────────────────────────────────────────────────────────────────────────────
if ! command -v php2node &> /dev/null; then
    echo ""
    error_msg "La herramienta php2node no está instalada o el entorno virtual no está activo."
    echo ""
    echo "  Activa el entorno virtual y vuelve a intentar:"
    echo ""
    echo "    source .venv/Scripts/activate   (Windows Git Bash)"
    echo "    source .venv/bin/activate        (Mac/Linux)"
    echo ""
    echo "  Si es la primera vez, ejecuta:"
    echo ""
    echo "    bash setup.sh"
    echo ""
    exit 1
fi

# ─────────────────────────────────────────────────────────────────────────────
# Pantalla de bienvenida
# ─────────────────────────────────────────────────────────────────────────────
clear
linea
echo -e "${CYAN}       XIB — Herramienta de Migración PHP → NestJS${RESET}"
echo -e "${CYAN}       Transformación • akisi_backend_nestjs${RESET}"
linea
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PASO 1 — Endpoint
# ─────────────────────────────────────────────────────────────────────────────
linea_sm
titulo "[1/6]  Endpoint a migrar"
echo "       Escribe la ruta sin barra inicial."
echo "       Ejemplo: bank_account/dacustomer_bank"
echo ""
while true; do
    read -rp "  > " ENDPOINT_PATH
    ENDPOINT_PATH="${ENDPOINT_PATH// /}"   # quitar espacios
    if [[ -n "$ENDPOINT_PATH" ]]; then
        break
    fi
    warn "El endpoint no puede estar vacío."
done
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PASO 2 — Método HTTP
# ─────────────────────────────────────────────────────────────────────────────
linea_sm
titulo "[2/6]  Método HTTP"
echo ""
echo "       1) GET"
echo "       2) POST"
echo "       3) PUT"
echo "       4) DELETE"
echo ""
while true; do
    read -rp "  Elige una opción (1-4): " HTTP_OPCION
    case "$HTTP_OPCION" in
        1) HTTP_METHOD="GET";    break ;;
        2) HTTP_METHOD="POST";   break ;;
        3) HTTP_METHOD="PUT";    break ;;
        4) HTTP_METHOD="DELETE"; break ;;
        *) warn "Opción inválida. Elige entre 1 y 4." ;;
    esac
done
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PASO 3 — Versión
# ─────────────────────────────────────────────────────────────────────────────
linea_sm
titulo "[3/6]  Versión del inventario"
echo ""
echo "       1) v1"
echo "       2) v2"
echo "       3) Detectar automáticamente"
echo ""
while true; do
    read -rp "  Elige una opción (1-3): " VERSION_OPCION
    case "$VERSION_OPCION" in
        1) VERSION_ARG="v1"; break ;;
        2) VERSION_ARG="v2"; break ;;
        3) VERSION_ARG="";   break ;;
        *) warn "Opción inválida. Elige entre 1 y 3." ;;
    esac
done
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PASO 4 — Microservicio nuevo o existente
# ─────────────────────────────────────────────────────────────────────────────
linea_sm
titulo "[4/6]  ¿El microservicio es nuevo o ya existe en el repo NestJS?"
echo ""
echo "       1) Nuevo  — genera microservicio completo + Dockerfile + docker-compose"
echo "       2) Existente — genera solo los archivos del endpoint a integrar"
echo ""
while true; do
    read -rp "  Elige una opción (1-2): " MS_OPCION
    case "$MS_OPCION" in
        1) ES_NUEVO=true;  MS_NEW_FLAG="--ms-new"; break ;;
        2) ES_NUEVO=false; MS_NEW_FLAG="";         break ;;
        *) warn "Opción inválida. Elige 1 o 2." ;;
    esac
done
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PASO 5 — Nombre del microservicio
# ─────────────────────────────────────────────────────────────────────────────
linea_sm
titulo "[5/6]  Nombre del microservicio"
echo "       Solo el nombre, sin el prefijo msa-."
echo "       Ejemplo: bank-account  →  se creará msa-bank-account"
echo ""
while true; do
    read -rp "  > " MS_NAME_INPUT
    MS_NAME_INPUT="${MS_NAME_INPUT// /}"
    MS_NAME_INPUT="${MS_NAME_INPUT,,}"   # lowercase
    if [[ -n "$MS_NAME_INPUT" ]]; then
        break
    fi
    warn "El nombre del microservicio no puede estar vacío."
done
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# PASO 6 — Puerto (solo si es nuevo)
# ─────────────────────────────────────────────────────────────────────────────
MS_PORT_FLAG=""

if [[ "$ES_NUEVO" == true ]]; then
    linea_sm
    titulo "[6/6]  Puerto del microservicio"

    # Intentar detectar puerto automáticamente desde docker-compose.yml
    COMPOSE_FILE="${AKISI_REPO_ROOT:-}/docker-compose.yml"
    PUERTO_SUGERIDO=3003

    if [[ -f "$COMPOSE_FILE" ]]; then
        # Extraer puertos usados y calcular el siguiente disponible
        PUERTOS_USADOS=$(grep -oP '"\K\d{4,5}(?=:\d{4,5}")' "$COMPOSE_FILE" 2>/dev/null | sort -n | uniq || true)
        CANDIDATO=3003
        while echo "$PUERTOS_USADOS" | grep -q "^${CANDIDATO}$"; do
            CANDIDATO=$((CANDIDATO + 1))
        done
        PUERTO_SUGERIDO=$CANDIDATO
        echo ""
        echo "       Puertos detectados en docker-compose.yml: $(echo $PUERTOS_USADOS | tr '\n' ' ')"
        echo "       Puerto sugerido: ${PUERTO_SUGERIDO}"
    else
        echo ""
        echo "       No se encontró docker-compose.yml en: ${AKISI_REPO_ROOT:-<no configurado>}"
        echo "       Puerto sugerido por defecto: ${PUERTO_SUGERIDO}"
    fi

    echo ""
    echo "       Presiona Enter para usar el puerto sugerido (${PUERTO_SUGERIDO})"
    echo "       o escribe otro número de puerto:"
    echo ""
    read -rp "  > " PUERTO_INPUT

    if [[ -z "$PUERTO_INPUT" ]]; then
        MS_PORT="$PUERTO_SUGERIDO"
    else
        MS_PORT="$PUERTO_INPUT"
    fi

    MS_PORT_FLAG="--ms-port ${MS_PORT}"
    echo ""
else
    titulo "[6/6]  Puerto — No aplica para microservicio existente"
    echo ""
fi

# ─────────────────────────────────────────────────────────────────────────────
# Seleccionar inventario según versión
# ─────────────────────────────────────────────────────────────────────────────
INV_PATH=""
if [[ "$VERSION_ARG" == "v1" && -n "${PHP2NODE_INVENTORY_V1_XLSX:-}" ]]; then
    INV_PATH="${PHP2NODE_INVENTORY_V1_XLSX}"
elif [[ "$VERSION_ARG" == "v2" && -n "${PHP2NODE_INVENTORY_V2_XLSX:-}" ]]; then
    INV_PATH="${PHP2NODE_INVENTORY_V2_XLSX}"
elif [[ -n "${PHP2NODE_INVENTORY_V2_XLSX:-}" ]]; then
    INV_PATH="${PHP2NODE_INVENTORY_V2_XLSX}"
elif [[ -n "${PHP2NODE_INVENTORY_V1_XLSX:-}" ]]; then
    INV_PATH="${PHP2NODE_INVENTORY_V1_XLSX}"
fi

# Convertir backslashes a forward slashes (compatibilidad Windows)
INV_PATH="${INV_PATH//\\//}"
AKISI_ROOT_CLEAN="${AKISI_REPO_ROOT:-}"
AKISI_ROOT_CLEAN="${AKISI_ROOT_CLEAN//\\//}"

# ─────────────────────────────────────────────────────────────────────────────
# Resumen antes de ejecutar
# ─────────────────────────────────────────────────────────────────────────────
clear
linea
echo -e "${BLANCO}   RESUMEN — Verificar antes de continuar${RESET}"
linea
echo ""
echo "   Endpoint      : ${HTTP_METHOD} ${ENDPOINT_PATH}"
if [[ -n "$VERSION_ARG" ]]; then
    echo "   Versión       : ${VERSION_ARG}"
else
    echo "   Versión       : Detectar automáticamente"
fi
echo "   Microservicio : msa-${MS_NAME_INPUT}"
if [[ "$ES_NUEVO" == true ]]; then
    echo "   Tipo          : NUEVO (se genera estructura completa)"
    echo "   Puerto        : ${MS_PORT}"
else
    echo "   Tipo          : EXISTENTE (se generan archivos de integración)"
fi
echo "   Output en     : ${PHP2NODE_OUT:-./out}"
echo ""
linea
echo ""

read -rp "  ¿Proceder con la migración? (s/n): " CONFIRMAR_EJECUCION
if [[ "$CONFIRMAR_EJECUCION" != "s" && "$CONFIRMAR_EJECUCION" != "S" ]]; then
    echo ""
    warn "Operación cancelada por el usuario."
    echo ""
    exit 0
fi

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Construir y ejecutar el comando usando array (evita problemas con rutas Windows)
# ─────────────────────────────────────────────────────────────────────────────
linea
echo -e "${CYAN}   Ejecutando migración...${RESET}"
linea
echo ""
echo ""

# Array de argumentos — maneja rutas con espacios y backslashes correctamente
CMD_ARGS=(
    "--http-method" "$HTTP_METHOD"
    "--endpoint-path" "$ENDPOINT_PATH"
    "--ms-name" "$MS_NAME_INPUT"
)

[[ -n "$VERSION_ARG" ]]     && CMD_ARGS+=("--version" "$VERSION_ARG")
[[ "$ES_NUEVO" == true ]]   && CMD_ARGS+=("--ms-new")
[[ "$ES_NUEVO" == true ]]   && CMD_ARGS+=("--ms-port" "$MS_PORT")
[[ -n "$INV_PATH" ]]        && CMD_ARGS+=("--inventory-xlsx" "$INV_PATH")
[[ -n "$AKISI_ROOT_CLEAN" ]] && CMD_ARGS+=("--akisi-root" "$AKISI_ROOT_CLEAN")
CMD_ARGS+=("-v")

echo "  Comando: php2node ${CMD_ARGS[*]}"
echo ""

# Ejecutar directamente sin eval
php2node "${CMD_ARGS[@]}"
EXIT_CODE=$?

echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Resultado
# ─────────────────────────────────────────────────────────────────────────────
linea
if [[ $EXIT_CODE -eq 0 ]]; then
    ok "Migración completada exitosamente."
    echo ""
    echo "  Revisa el output en: ${PHP2NODE_OUT:-./out}"
    echo ""
    echo "  Archivos generados:"
    echo "    - msa-${MS_NAME_INPUT}/             → código del microservicio"
    echo "    - gateway-changes/                  → parches para mdl-billetera"
    if [[ "$ES_NUEVO" == true ]]; then
    echo "    - docker-compose.patch.yml          → bloque para el compose"
    fi
    echo "    - instrucciones.md                  → pasos para el dev"
    echo "    - report.md / changes.md            → análisis técnico"
else
    echo ""
    error_msg "La migración finalizó con errores (código: ${EXIT_CODE})."
    echo ""
    echo "  Revisa los mensajes de error de arriba."
    echo "  Si el endpoint no se encontró, verifica:"
    echo "    - Que el endpoint existe en el Excel de inventario"
    echo "    - Que la versión (v1/v2) sea correcta"
    echo "    - Que PHP2NODE_REPO_ROOT apunte al repo correcto en tu .env"
fi
linea
echo ""

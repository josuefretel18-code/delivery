# =====================================================================
# Programa el reporte diario multiagente con Google Cloud Scheduler
#
#   Cloud Scheduler (23:00, hora de Lima) --POST--> Render
#   /api/automatizacion/reporte-diario  (cabecera X-Automatizacion-Key)
#
# Cloud Scheduler: 3 tareas gratis por cuenta de facturacion (cobra por
# tarea creada, no por ejecucion). Esta es 1 tarea.
#
# Uso (desde la raiz del proyecto, con gcloud configurado):
#   powershell -ExecutionPolicy Bypass -File scripts\programar_reporte_gcp.ps1
#
# Al final muestra la clave para copiarla en Render como
# AUTOMATIZACION_KEY. Para reutilizar una clave existente:
#   ... programar_reporte_gcp.ps1 -Clave "la-clave-actual"
# =====================================================================

param(
    [string]$Region = "us-central1",
    [string]$Url = "https://kimbos-delivery.onrender.com",
    [string]$Horario = "0 23 * * *",
    [string]$Clave = ""
)

$ErrorActionPreference = "Continue"

if (Get-Command gcloud.cmd -ErrorAction SilentlyContinue) {
    Set-Alias -Name gcloud -Value gcloud.cmd -Scope Script
}

function Paso($texto) {
    Write-Host ""
    Write-Host "==> $texto" -ForegroundColor Cyan
}

function Verificar($descripcion) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR en: $descripcion (codigo $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

$Tarea = "kimbos-reporte-diario"
$Destino = "$Url/api/automatizacion/reporte-diario"

# ---------------------------------------------------------------------
Paso "Proyecto"
# ---------------------------------------------------------------------

$Proyecto = (gcloud config get-value project 2>$null).Trim()
if (-not $Proyecto) {
    Write-Host "No hay proyecto configurado. Ejecuta: gcloud init" -ForegroundColor Red
    exit 1
}
Write-Host "Proyecto: $Proyecto | Region: $Region | Destino: $Destino"

# ---------------------------------------------------------------------
Paso "Habilitando Cloud Scheduler"
# ---------------------------------------------------------------------

gcloud services enable cloudscheduler.googleapis.com
Verificar "habilitar Cloud Scheduler"

# ---------------------------------------------------------------------
Paso "Clave de la automatizacion"
# ---------------------------------------------------------------------

if (-not $Clave) {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $Clave = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()
    Write-Host "Se genero una clave nueva."
}

# ---------------------------------------------------------------------
Paso "Tarea programada ($Horario, America/Lima)"
# ---------------------------------------------------------------------

# Render (plan free) puede tardar 30-60 s en despertar: plazo de 5 min
# y 2 reintentos si falla.
$Opciones = @(
    "--location=$Region",
    "--schedule=$Horario",
    "--time-zone=America/Lima",
    "--uri=$Destino",
    "--http-method=POST",
    "--message-body={}",
    "--attempt-deadline=300s",
    "--max-retry-attempts=2",
    "--min-backoff=60s"
)

gcloud scheduler jobs describe $Tarea --location=$Region 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    gcloud scheduler jobs update http $Tarea @Opciones `
        "--update-headers=X-Automatizacion-Key=$Clave,Content-Type=application/json"
    Verificar "actualizar tarea"
} else {
    gcloud scheduler jobs create http $Tarea @Opciones `
        "--headers=X-Automatizacion-Key=$Clave,Content-Type=application/json"
    Verificar "crear tarea"
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host " Reporte diario programado: todos los dias a las 23:00 (Lima)" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "1) En Render > Environment agrega (no la compartas):"
Write-Host "     AUTOMATIZACION_KEY = $Clave"
Write-Host ""
Write-Host "2) Cuando Render termine de redesplegar, prueba la tarea ahora:"
Write-Host "     gcloud scheduler jobs run $Tarea --location=$Region"
Write-Host ""
Write-Host "3) Revisa el resultado en el panel admin > Reporte diario, o en:"
Write-Host "     Google Cloud Console > Cloud Scheduler > $Tarea"
Write-Host ""

# =====================================================================
# Mantiene despierto el servidor de Render en horario de atencion
#
# Render (plan free) apaga el servidor tras 15 min sin visitas y la
# primera visita tarda 30-60 s. Cloud Scheduler visita /api/health cada
# 10 minutos de 10:00 a 21:50 (hora de Lima): la tienda abre a las
# 11:00, asi ya esta despierta, y cierra a las 22:00.
#
# Cloud Scheduler: 3 tareas gratis por cuenta (se cobra por tarea, no
# por ejecucion). Esta es la 2.a (la 1.a es el reporte diario).
# Render free incluye 750 horas al mes: 12 h diarias son ~372 h.
#
# Uso (desde la raiz del proyecto, con gcloud configurado):
#   powershell -ExecutionPolicy Bypass -File scripts\mantener_activo_gcp.ps1
# =====================================================================

param(
    [string]$Region = "us-central1",
    [string]$Url = "https://kimbos-delivery.onrender.com",
    [string]$Horario = "*/10 10-21 * * *"
)

$ErrorActionPreference = "Continue"

if (Get-Command gcloud.cmd -ErrorAction SilentlyContinue) {
    Set-Alias -Name gcloud -Value gcloud.cmd -Scope Script
}

function Verificar($descripcion) {
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR en: $descripcion (codigo $LASTEXITCODE)" -ForegroundColor Red
        exit 1
    }
}

$Tarea = "kimbos-mantener-activo"
$Destino = "$Url/api/health"

$Proyecto = (gcloud config get-value project 2>$null).Trim()
if (-not $Proyecto) {
    Write-Host "No hay proyecto configurado. Ejecuta: gcloud init" -ForegroundColor Red
    exit 1
}

Write-Host "Proyecto: $Proyecto | Destino: $Destino | Horario: $Horario (America/Lima)"

gcloud services enable cloudscheduler.googleapis.com
Verificar "habilitar Cloud Scheduler"

$Opciones = @(
    "--location=$Region",
    "--schedule=$Horario",
    "--time-zone=America/Lima",
    "--uri=$Destino",
    "--http-method=GET",
    "--attempt-deadline=120s",
    "--max-retry-attempts=1"
)

gcloud scheduler jobs describe $Tarea --location=$Region 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    gcloud scheduler jobs update http $Tarea @Opciones
    Verificar "actualizar tarea"
} else {
    gcloud scheduler jobs create http $Tarea @Opciones
    Verificar "crear tarea"
}

Write-Host ""
Write-Host "Listo: Render se mantendra despierto de 10:00 a 22:00 (Lima)." -ForegroundColor Green
Write-Host "Probar ahora:  gcloud scheduler jobs run $Tarea --location=$Region"
Write-Host ""

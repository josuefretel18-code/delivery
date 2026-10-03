# =====================================================================
# Despliegue del servicio de Machine Learning en Google Cloud
#
#   Cloud Storage   : dataset DoorDash, modelo, metricas, historial
#   Cloud Run Job   : kimbos-ml-entrenamiento (entrena el modelo)
#   Cloud Run       : kimbos-ml (API de prediccion y metricas)
#   Secret Manager  : DATABASE_URL y ML_API_KEY
#
# Uso (desde la raiz del proyecto, con gcloud configurado):
#   powershell -ExecutionPolicy Bypass -File scripts\desplegar_ml_gcp.ps1
#
# Se puede volver a ejecutar para publicar cambios de codigo: lo que
# ya existe se reutiliza. Para subir solo codigo (sin tocar datos):
#   powershell -ExecutionPolicy Bypass -File scripts\desplegar_ml_gcp.ps1 -SoloCodigo
# =====================================================================

param(
    [string]$Region = "us-central1",
    [switch]$SoloCodigo
)

# "Continue": en Windows PowerShell 5.1, con "Stop" redirigir los
# errores de gcloud (2>$null) detiene el script cuando un recurso aun
# no existe. Los errores reales se revisan con Verificar.
$ErrorActionPreference = "Continue"

# Usar gcloud.cmd para que $LASTEXITCODE refleje el resultado.
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

function Crear-Secreto($nombre, $valor) {
    # Archivo temporal sin salto de linea final (PowerShell agrega uno
    # al usar tuberias y el secreto quedaria con un caracter de mas).
    $tmp = [System.IO.Path]::GetTempFileName()
    try {
        [System.IO.File]::WriteAllText($tmp, $valor)
        gcloud secrets describe $nombre --format="value(name)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            gcloud secrets versions add $nombre --data-file=$tmp | Out-Null
        } else {
            gcloud secrets create $nombre --replication-policy=automatic --data-file=$tmp | Out-Null
        }
        Verificar "secreto $nombre"
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

# ---------------------------------------------------------------------
Paso "Proyecto y facturacion"
# ---------------------------------------------------------------------

$Proyecto = (gcloud config get-value project 2>$null).Trim()
if (-not $Proyecto) {
    Write-Host "No hay proyecto configurado. Ejecuta: gcloud init" -ForegroundColor Red
    exit 1
}

$Facturacion = (gcloud billing projects describe $Proyecto --format="value(billingEnabled)" 2>$null)
if ($Facturacion -ne "True") {
    Write-Host "El proyecto $Proyecto no tiene facturacion activada." -ForegroundColor Red
    exit 1
}

$NumeroProyecto = (gcloud projects describe $Proyecto --format="value(projectNumber)").Trim()

$Bucket = "$Proyecto-kimbos-ml"
$CuentaServicio = "kimbos-ml@$Proyecto.iam.gserviceaccount.com"
$Imagen = "$Region-docker.pkg.dev/$Proyecto/kimbos/kimbos-ml:latest"
$Job = "kimbos-ml-entrenamiento"
$Servicio = "kimbos-ml"

Write-Host "Proyecto: $Proyecto | Region: $Region | Bucket: gs://$Bucket"

if (-not $SoloCodigo) {

    # -----------------------------------------------------------------
    Paso "Habilitando APIs (puede tardar 1-2 min)"
    # -----------------------------------------------------------------

    gcloud services enable run.googleapis.com cloudbuild.googleapis.com `
        artifactregistry.googleapis.com storage.googleapis.com `
        secretmanager.googleapis.com iam.googleapis.com
    Verificar "habilitar APIs"

    # -----------------------------------------------------------------
    Paso "Repositorio de imagenes (Artifact Registry)"
    # -----------------------------------------------------------------

    gcloud artifacts repositories describe kimbos --location=$Region 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        gcloud artifacts repositories create kimbos --repository-format=docker `
            --location=$Region --description="Imagenes de Kimbos"
        Verificar "crear repositorio"
    }

    # -----------------------------------------------------------------
    Paso "Bucket de Cloud Storage"
    # -----------------------------------------------------------------

    gcloud storage buckets describe "gs://$Bucket" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        gcloud storage buckets create "gs://$Bucket" --location=$Region --uniform-bucket-level-access
        Verificar "crear bucket"
    }

    # -----------------------------------------------------------------
    Paso "Subiendo dataset, modelo y metricas al bucket"
    # -----------------------------------------------------------------

    $Archivos = @(
        "ml/data/externo/historical_data.csv",
        "ml/data/dataset_info.json",
        "ml/models/modelo_final.joblib",
        "ml/metrics/metricas.json",
        "ml/metrics/comparacion_modelos.csv",
        "ml/metrics/matriz_confusion.png",
        "ml/metrics/historial_modelos.json"
    )

    foreach ($archivo in $Archivos) {
        if (Test-Path $archivo) {
            gcloud storage cp $archivo "gs://$Bucket/$archivo"
            Verificar "subir $archivo"
        } else {
            Write-Host "  (no existe, se omite) $archivo" -ForegroundColor Yellow
        }
    }

    # -----------------------------------------------------------------
    Paso "Cuenta de servicio y permisos"
    # -----------------------------------------------------------------

    gcloud iam service-accounts describe $CuentaServicio 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        gcloud iam service-accounts create kimbos-ml --display-name="Kimbos ML"
        Verificar "crear cuenta de servicio"
    }

    # Leer y escribir archivos del ML en el bucket
    gcloud storage buckets add-iam-policy-binding "gs://$Bucket" `
        --member="serviceAccount:$CuentaServicio" --role="roles/storage.objectAdmin" | Out-Null
    Verificar "permiso bucket"

    # Lanzar el job y consultar sus ejecuciones; leer secretos; logs
    foreach ($rol in @("roles/run.developer", "roles/secretmanager.secretAccessor", "roles/logging.logWriter")) {
        gcloud projects add-iam-policy-binding $Proyecto `
            --member="serviceAccount:$CuentaServicio" --role=$rol --condition=None | Out-Null
        Verificar "rol $rol"
    }

    # Lanzar un job que corre con esta misma cuenta de servicio
    gcloud iam service-accounts add-iam-policy-binding $CuentaServicio `
        --member="serviceAccount:$CuentaServicio" --role="roles/iam.serviceAccountUser" | Out-Null
    Verificar "actAs"

    # Cloud Build (construye la imagen) usa la cuenta de Compute por defecto
    gcloud projects add-iam-policy-binding $Proyecto `
        --member="serviceAccount:$NumeroProyecto-compute@developer.gserviceaccount.com" `
        --role="roles/cloudbuild.builds.builder" --condition=None | Out-Null
    Verificar "permiso Cloud Build"

    # -----------------------------------------------------------------
    Paso "Secretos (Secret Manager)"
    # -----------------------------------------------------------------

    $LineaDb = Get-Content .env | Where-Object { $_ -match '^\s*DATABASE_URL\s*=' } | Select-Object -First 1
    if (-not $LineaDb) {
        Write-Host "No se encontro DATABASE_URL en .env" -ForegroundColor Red
        exit 1
    }
    $DatabaseUrl = ($LineaDb -replace '^\s*DATABASE_URL\s*=\s*', '').Trim().Trim('"').Trim("'")
    Crear-Secreto "kimbos-database-url" $DatabaseUrl

    # La clave de la API se crea una sola vez y se reutiliza.
    gcloud secrets describe kimbos-ml-api-key --format="value(name)" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $bytes = New-Object byte[] 32
        [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
        $ClaveApi = [System.BitConverter]::ToString($bytes).Replace("-", "").ToLower()
        Crear-Secreto "kimbos-ml-api-key" $ClaveApi
    }
}

# ---------------------------------------------------------------------
Paso "Construyendo la imagen en Cloud Build (3-6 min)"
# ---------------------------------------------------------------------

gcloud builds submit --tag $Imagen .
Verificar "construir imagen"

# ---------------------------------------------------------------------
Paso "Cloud Run Job de entrenamiento"
# ---------------------------------------------------------------------

gcloud run jobs deploy $Job --image=$Imagen --region=$Region `
    --service-account=$CuentaServicio `
    --command=python --args="ml/job_entrenamiento.py" `
    --cpu=2 --memory=4Gi --task-timeout=1800 --max-retries=0 `
    --set-env-vars="ML_BUCKET=$Bucket,ML_N_JOBS=2,REPARTIDORES_DISPONIBLES=2" `
    --set-secrets="DATABASE_URL=kimbos-database-url:latest"
Verificar "desplegar job"

# ---------------------------------------------------------------------
Paso "Cloud Run: API de ML"
# ---------------------------------------------------------------------

gcloud run deploy $Servicio --image=$Imagen --region=$Region `
    --service-account=$CuentaServicio --allow-unauthenticated `
    --cpu=1 --memory=1Gi --min-instances=0 --max-instances=2 --timeout=120 `
    --set-env-vars="ML_BUCKET=$Bucket,ML_JOB=projects/$Proyecto/locations/$Region/jobs/$Job,REPARTIDORES_DISPONIBLES=2" `
    --set-secrets="ML_API_KEY=kimbos-ml-api-key:latest"
Verificar "desplegar servicio"

$Url = (gcloud run services describe $Servicio --region=$Region --format="value(status.url)").Trim()

# ---------------------------------------------------------------------
Paso "Comprobacion"
# ---------------------------------------------------------------------

try {
    $Salud = Invoke-RestMethod -Uri "$Url/salud" -TimeoutSec 60
    Write-Host ("/salud -> ok=" + $Salud.ok + " modelo=" + $Salud.modelo_version + " almacen=" + $Salud.almacen) -ForegroundColor Green
} catch {
    Write-Host "No respondio /salud todavia: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host " API de ML desplegada: $Url" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Configura en Render (Environment) estas dos variables:"
Write-Host "  ML_API_URL = $Url"
Write-Host "  ML_API_KEY = (ejecuta el comando de abajo y copia el resultado)"
Write-Host ""
Write-Host "  gcloud secrets versions access latest --secret=kimbos-ml-api-key"
Write-Host ""

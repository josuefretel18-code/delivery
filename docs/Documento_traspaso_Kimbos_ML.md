# Documento de Traspaso del Proyecto — Kimbos Delivery

> Versión actualizada al **03/10/2026**. Reemplaza a los documentos
> anteriores (el modelo con datos sintéticos fue descartado).

## 1. Objetivo del sistema

**Nombre:** Implementación de un Sistema Web de Gestión y Seguimiento de
Pedidos Delivery con Predicción de Retrasos mediante Machine Learning.

Kimbos (caso académico, Cerro de Pasco – Perú) gestiona pedidos delivery,
catálogo, usuarios y estados. Usa Google Maps para ubicación, distancia y ruta,
PostgreSQL como base de datos y Machine Learning para predecir si un pedido
tiene riesgo de retrasarse.

Flujo principal:

Cliente → catálogo → carrito → ubicación → ruta → pedido → **predicción ML** →
preparación → en ruta → entrega → **resultado real** → comparación →
**reentrenamiento automático en Google Cloud**.

---

## 2. Arquitectura en producción

```text
        RENDER (sistema web)                        GOOGLE CLOUD (solo ML)
┌──────────────────────────────┐         ┌──────────────────────────────────────┐
│ kimbos-delivery              │  HTTPS  │ Cloud Run: kimbos-ml (API de ML)     │
│ Flask + Gunicorn             │────────►│  POST /predecir   riesgo de retraso  │
│ tienda, pedidos, panel admin,│ X-API-  │  GET  /metricas   métricas, matriz,  │
│ dashboard ML                 │   Key   │                   historial, estado  │
│                              │         │  POST /reentrenar lanza el job       │
│ crear pedido  → /predecir    │         │  GET  /salud                         │
│ entregar      → /reentrenar  │         └───────┬──────────────────────────────┘
│ dashboard     → /metricas    │                 │ lanza
└──────────────┬───────────────┘         ┌───────▼──────────────────────────────┐
               │                         │ Cloud Run Job: kimbos-ml-entrenamiento│
               │                         │ (2 vCPU, 4 GB) exportar + entrenar   │
               │                         └───────┬──────────────────────────────┘
               │                                 │ lee / guarda
               │                         ┌───────▼──────────────────────────────┐
               │                         │ Cloud Storage: dataset DoorDash,     │
               │                         │ modelo activo, métricas, matriz de   │
               │                         │ confusión, historial de versiones    │
               │                         └──────────────────────────────────────┘
               ▼
     PostgreSQL en Aiven (pedidos y predicciones) ◄── el job lee los pedidos reales
```

| Componente | Dónde | Identificador |
|---|---|---|
| Sistema web | Render (plan free) | https://kimbos-delivery.onrender.com |
| API de ML | Google Cloud Run | https://kimbos-ml-7qyvn27tpq-uc.a.run.app |
| Entrenamiento | Cloud Run Job | `kimbos-ml-entrenamiento` |
| Archivos del ML | Cloud Storage | `gs://gmp-demo-project-483664027-kimbos-ml` |
| Secretos del ML | Secret Manager | `kimbos-database-url`, `kimbos-ml-api-key` |
| Imagen del ML | Artifact Registry | `us-central1-docker.pkg.dev/gmp-demo-project-483664027/kimbos/kimbos-ml` |
| Base de datos | Aiven PostgreSQL | `delivery_db` |

Proyecto de Google Cloud: **Maps Platform Project**
(`gmp-demo-project-483664027`), región `us-central1`. Es el mismo proyecto de
la API Key de Google Maps.

### Tecnologías

- Backend: Python + Flask (REST), Gunicorn. Render usa Python 3.10
  (`.python-version`); el contenedor de ML usa Python 3.11 (`Dockerfile`).
- Base de datos: PostgreSQL en Aiven.
- Frontend: HTML, CSS, JavaScript, Bootstrap.
- Mapas: Google Maps JavaScript API, Places API (New), Routes API (solo en el
  navegador). La API Key "Delivery Maps Key" está restringida por URL de
  referencia: incluye `localhost`, `127.0.0.1` y
  `https://kimbos-delivery.onrender.com/*`.
- Autenticación: JWT. Roles: CLIENTE, OPERADOR, ADMIN, REPARTIDOR.
- ML: pandas, NumPy, scikit-learn 1.7.2, joblib, matplotlib.
- Google Cloud: Cloud Run, Cloud Run Jobs, Cloud Storage, Secret Manager,
  Artifact Registry, Cloud Build.

### Reglas de negocio

- Estados: `REGISTRADO → PREPARANDO → EN_RUTA → ENTREGADO`.
- Delivery: `S/ 3.00 + S/ 1.20 × distancia_km` (calculado en el backend).
- Al pasar a ENTREGADO se calculan `duracion_real_min` y
  `retraso = duración real > tiempo_estimado_total_min + 5 min`.
- `pedidos.fuente_datos` distingue `REAL` de `SINTETICO_ML`.

---

## 3. Reglas de comportamiento para la IA que continúe

- Responder en español; ser directa y práctica; una etapa a la vez.
- Dar comandos exactos de PowerShell cuando corresponda.
- **No inventar datos, métricas ni resultados.** Las métricas vigentes están en
  Cloud Storage (`ml/metrics/metricas.json`); las copias del repositorio pueden
  estar desactualizadas.
- Revisar el resultado de cada paso antes de continuar.
- Corregir al usuario cuando haya un error; no dar la razón automáticamente.
- Explicar de forma sencilla para una exposición universitaria.
- Cambios de código: revisar el archivo, cambio mínimo, comprobar.

### Seguridad

No pedir contraseñas, `DATABASE_URL`, `JWT_SECRET_KEY`, `MAPS_API_KEY`,
`ML_API_KEY` ni tokens. El `.env` está ignorado por Git.

### Decisiones del docente / ingeniero (no revertir)

- **No se aceptan datos sintéticos.** Los 1,000 registros `SINTETICO_ML`
  siguen en la BD solo como respaldo: no se muestran ni se usan.
- El modelo se entrena con **datos reales**: dataset público DoorDash +
  pedidos reales de Kimbos.
- El modelo **se mejora con los registros nuevos**: reentrenamiento automático
  al entregar cada pedido.
- **El ML se despliega en Google Cloud, separado de Render.** Render solo
  aloja el sistema web.

---

## 4. Machine Learning

### Datos de entrenamiento

| Fuente | Registros | Detalle |
|---|---|---|
| DoorDash ETA Prediction (Kaggle) | 197,428 → **176,097** tras limpieza | Entregas reales oct. 2014 – feb. 2015 (EE. UU.), con ruido añadido por DoorDash |
| Pedidos reales de Kimbos entregados | **7** (al 03/10/2026) | Tabla `pedidos`, `fuente_datos = REAL` |

- El CSV externo (`historical_data.csv`) está en Cloud Storage
  (`ml/data/externo/`) y en local en `ml/data/externo/` (no está en Git).
- Limpieza: sin nulos en tiempos/carga; ≥ 1 repartidor en turno y ≥ 1 pedido
  pendiente; duración real entre 10 y 180 min; ruta > 0; máximo 30 ítems.
- Zona horaria: DoorDash viene en UTC; se convierte a `America/Los_Angeles`
  (suposición: así los picos caen a las 12 h y 18 h).
- **Regla de retraso**:
  - DoorDash (no trae hora prometida): estimado = ruta + envío al restaurante +
    **29.9 min** de preparación típica (mediana del dataset). Retraso si
    real > estimado + 5 min (37.5 % de retrasos).
  - Kimbos: real > ruta + preparación estimada + 5 min.
- Detalle en `ml/data/dataset_info.json`.

### Variables del modelo (7) — definidas en `ml/variables.py`

`duracion_estimada_min`, `cantidad_items`, `hora_pedido`, `dia_semana`,
`hora_pico` (12–14 y 19–21), `fin_semana` (vie–dom), `carga_repartidor`.

- `carga_repartidor = pedidos activos ÷ repartidores disponibles`. Es
  comparable entre DoorDash (~41 pedidos activos) y Kimbos (0–3), y es la
  variable más predictiva. Kimbos usa `REPARTIDORES_DISPONIBLES` (2).
- `distancia_km` y `tiempo_preparacion_estimado_min` se guardan en
  `predicciones_ml` pero no son entradas (DoorDash no las tiene).
- Objetivo: `retraso` (0 = A tiempo, 1 = Retrasado).

### Modelo activo: v5.0 (Random Forest)

Entrenado en Google Cloud el 03/10/2026 (reentrenamiento automático) con
176,104 registros (176,097 DoorDash + 7 Kimbos). División 80/20
estratificada; validación cruzada estratificada de 5 folds; selección por
mayor F1 promedio de CV. Prueba con 35,221 registros:

| Modelo | F1 CV | Accuracy | Precision | Recall | F1 test | ROC-AUC |
|---|---|---|---|---|---|---|
| Regresión Logística | 0.6026 | 67.6 % | 55.7 % | 66.1 % | 0.6046 | 0.7306 |
| **Random Forest** ✓ | **0.6068** | 70.0 % | 59.5 % | 62.4 % | 0.6092 | 0.7482 |
| Gradient Boosting | 0.6052 | 69.9 % | 59.3 % | 62.7 % | 0.6091 | 0.7490 |

Matriz de confusión (v5.0): `[[16412, 5603], [4968, 8238]]`
(filas = real A tiempo / Retrasado; columnas = predicho).

Notas para la exposición:

- Random Forest y Gradient Boosting están prácticamente empatados.
- De v2.0 (0.6063) a v5.0 (0.6068) la mejora es mínima. Con 7 pedidos de
  Kimbos entre 176 mil **no** se debe afirmar que esos pedidos mejoraron el
  modelo. Lo correcto: *“el sistema reentrena con cada pedido entregado y
  solo cambia de modelo si las métricas mejoran”*.

### Historial de versiones

| Versión | Datos | Dónde se entrenó | Resultado |
|---|---|---|---|
| v1.0 | 1,000 sintéticos | Local | **Descartado** (`archivo_sintetico/`) |
| v2.0 | DoorDash + 4 Kimbos | Local | Anterior (RF, F1 CV 0.6063) |
| v3.0 | DoorDash + 5 Kimbos | Local | No mejoró (0.6062) |
| v4.0 | DoorDash + 6 Kimbos | Local | Anterior (GB, 0.6067) |
| v5.0 | DoorDash + 7 Kimbos | **Google Cloud** (automático) | **Activo** (RF, 0.6068) |

### Reentrenamiento

- **Automático**: al marcar un pedido como ENTREGADO, Render llama a
  `POST /reentrenar` de la API de ML, que lanza el Cloud Run Job (≈ 3 min).
  Variable `REENTRENAMIENTO_AUTOMATICO=true` en Render.
- El job descarga del bucket el dataset, el modelo y el historial; ejecuta
  `ml/reentrenar.py`; repite mientras haya pedidos reales nuevos (máx. 3
  vueltas) y sube los resultados.
- Solo se entrena si hay pedidos reales nuevos desde el último entrenamiento.
- La versión nueva **solo reemplaza a la activa si su F1 CV es igual o
  mayor**; si no, queda como “No mejoró”.
- Un solo entrenamiento a la vez (la API consulta las ejecuciones del job).
- La API de ML revisa cada 30 s si cambió el modelo en el bucket y lo recarga
  sin redesplegar.
- **Botón manual** en el dashboard: solo aparece si hay pedidos entregados sin
  procesar (el automático falló o está apagado), como “Reintentar
  reentrenamiento”.
- Si la API de ML no responde, **el pedido se registra igual sin predicción**.

### Panel administrativo — Dashboard ML

1. *Evaluación del modelo*: métricas, matriz de confusión, comparación de
   modelos, fuente del dataset y regla de retraso.
2. *Predicciones en pedidos reales*: tabla pedido por pedido (predicción vs.
   resultado real). Matriz y Precision/Recall/F1 de reales desde 30 evaluados.
   Excluye predicciones del modelo sintético v1.0.
3. *Evolución del modelo*: dónde se entrena (Google Cloud), estado
   (reentrenando / último resultado) y las 10 versiones más recientes.

---

## 5. Código

### Archivos principales

```text
app.py, db.py
backend/
├── ml_service.py          cliente de la API de ML (con ML_API_URL) o modelo local
├── ml_reentrenamiento.py  dispara el reentrenamiento (remoto o local)
└── routes/ pedidos.py (pedidos, predicción, dashboard ML), sedes.py, catalogo.py
frontend/ templates/{index,admin}.html, static/{css,js}/{cliente,admin}.*
ml/
├── servicio.py            API de ML (Cloud Run)
├── job_entrenamiento.py   entrenamiento (Cloud Run Job)
├── almacen.py             Cloud Storage (ML_BUCKET) o carpetas locales
├── prediccion.py          lógica de predicción
├── variables.py           variables y reglas comunes
├── exportar_dataset.py    DoorDash + Kimbos → pedidos_ml.csv
├── entrenar_modelo.py     3 modelos, CV, versión, promoción
├── reentrenar.py          exportar + entrenar (códigos 0/2/3)
└── archivo_sintetico/     generadores sintéticos (no se usan)
Dockerfile, requirements-ml.txt, .gcloudignore   imagen del ML
render.yaml, .python-version, requirements.txt   sistema web (Render)
scripts/desplegar_ml_gcp.ps1                     despliegue en Google Cloud
docs/Documento_traspaso_Kimbos_ML.md
```

### Endpoints del sistema web (Render)

| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/auth/registro`, `/api/auth/login` | público |
| GET | `/api/auth/me` | autenticado |
| GET | `/api/sedes/activa`, `/api/catalogo` | público |
| POST / PATCH | `/api/catalogo…` | ADMIN (disponibilidad: ADMIN, OPERADOR) |
| POST | `/api/pedidos` | CLIENTE, ADMIN, OPERADOR (pide predicción) |
| GET | `/api/pedidos/mis-pedidos` | autenticado |
| GET | `/api/pedidos` | ADMIN, OPERADOR (solo reales) |
| PATCH | `/api/pedidos/<id>/estado` | ADMIN, OPERADOR (ENTREGADO → reentrenamiento) |
| GET | `/api/pedidos/ml/resumen` | ADMIN, OPERADOR |
| POST | `/api/pedidos/ml/reentrenar` | ADMIN |
| GET | `/api/health`, `/api/database` | público |

### Variables de entorno

| Variable | Render | Cloud Run (API) | Cloud Run Job |
|---|---|---|---|
| `DATABASE_URL` | ✓ | — | ✓ (Secret Manager) |
| `JWT_SECRET_KEY`, `MAPS_API_KEY` | ✓ | — | — |
| `ML_API_URL`, `ML_API_KEY` | ✓ | `ML_API_KEY` (Secret Manager) | — |
| `ML_BUCKET` | — | ✓ | ✓ |
| `ML_JOB` | — | ✓ | — |
| `REPARTIDORES_DISPONIBLES` | ✓ (2) | ✓ (2) | ✓ (2) |
| `REENTRENAMIENTO_AUTOMATICO` | ✓ (true) | — | — |

Sin `ML_API_URL` (desarrollo local) el sistema usa el modelo y archivos locales
de `ml/`. El servicio de ML también puede correr en local:
`python ml/servicio.py` (puerto 8000).

---

## 6. Operación

### Ejecutar en local

```powershell
cd C:\Proyectos\delivery
.\.venv\Scripts\Activate.ps1
python app.py
```

### Publicar cambios

- **Sistema web**: `git push origin main` → Render redespliega solo.
- **Código del ML** (`ml/`, `Dockerfile`): desde la raíz, con `gcloud`
  configurado en el proyecto `gmp-demo-project-483664027`:
  ```powershell
  powershell -ExecutionPolicy Bypass -File scripts\desplegar_ml_gcp.ps1 -SoloCodigo
  ```
  (sin `-SoloCodigo` además revisa APIs, permisos y secretos, y sube al bucket
  solo los archivos que falten: nunca reemplaza el modelo vigente).
- Entrenar manualmente en la nube:
  `gcloud run jobs execute kimbos-ml-entrenamiento --region=us-central1 --update-env-vars=ORIGEN=MANUAL --wait`
- Traer el modelo vigente al equipo local:
  `gcloud storage cp -r gs://gmp-demo-project-483664027-kimbos-ml/ml/models gs://gmp-demo-project-483664027-kimbos-ml/ml/metrics ml/`

### Dónde ver todo en Google Cloud Console

Cloud Run → `kimbos-ml` (métricas y registros de la API) · Cloud Run → Jobs →
`kimbos-ml-entrenamiento` (ejecuciones y registros del entrenamiento) · Cloud
Storage → bucket → `ml/metrics/matriz_confusion.png`, `metricas.json`,
`historial_modelos.json`.

### Base de datos — migraciones aplicadas

`sql/adaptar_ml_pedidos.sql`, `sql/adaptar_predicciones_ml.sql`,
`sql/adaptar_predicciones_carga.sql` (`repartidores_disponibles` y
`carga_repartidor NUMERIC(8,4)` en `predicciones_ml`).

---

## 7. Problemas conocidos

1. **Arranque en frío**: Render (free) y Cloud Run (mín. 0 instancias) se
   apagan sin uso. La primera visita tarda 30–60 s (Render) y la primera
   predicción unos segundos más (Cloud Run). Abrir el sitio antes de presentar.
2. **Latencia**: cada petición a Render abre dos conexiones a Aiven (~5 s en
   local). Mejora pendiente: pool de conexiones.
3. **El aviso “Reentrenando”** puede tardar ~1 min en apagarse después de que
   termina el job (Google Cloud tarda en marcar la ejecución como terminada).
4. **Equipo de desarrollo**: archivo de paginación de 2 GB; con muchos
   programas abiertos el entrenamiento local falla por memoria (ya no afecta a
   producción, que entrena en Google Cloud).
5. **Python 3.10** (Render y `.venv`): Google deja de dar soporte en sus
   librerías desde el 04/10/2026. El contenedor de ML ya usa 3.11; conviene
   migrar Render y el `.venv` a 3.11.
6. `/api/database` es público y muestra el nombre de la BD y el usuario
   (no la contraseña). Conviene protegerlo o eliminarlo.

---

## 8. Siguientes pasos

1. Acumular pedidos reales cambiando los estados en el momento real, para
   que la sección 2 del dashboard llegue a 30 evaluados.
2. Proteger o eliminar `/api/database`.
3. Migrar Render y `.venv` a Python 3.11.
4. Opcional: pool de conexiones a PostgreSQL; rellenar nombre y teléfono del
   destinatario con los datos del cliente.

---

## Instrucción final para la IA que reciba este documento

**No comenzar desde cero, no volver a datos sintéticos y no mover el ML a
Render.**

El sistema está desplegado: web en Render y Machine Learning en Google Cloud
(API en Cloud Run, entrenamiento en Cloud Run Job, archivos en Cloud Storage),
con modelo v5.0 entrenado con datos reales, predicción en cada pedido,
dashboard con métricas y matriz de confusión, y reentrenamiento automático en
la nube al entregar cada pedido.

Antes de citar métricas, leer `ml/metrics/metricas.json` e
`historial_modelos.json` **desde Cloud Storage**, porque cambian con cada
reentrenamiento.

# Kimbos Delivery

Sistema de pedidos a domicilio para Kimbos (Cerro de Pasco, Perú) con
**Machine Learning** para predecir retrasos de entrega y un **sistema
multiagente con LLM** que analiza pedidos en riesgo y redacta un informe
operativo diario.

- Producción: <https://kimbos-delivery.onrender.com> (tienda) ·
  `/acceso` (ingreso del personal) · `/admin` · `/repartidor`
- Stack: Python 3.10 · Flask · PostgreSQL · scikit-learn · OpenAI
  (gpt-5-mini) · JavaScript + Bootstrap 5 · Render · Google Cloud

---

## Contenido

1. [Arquitectura](#1-arquitectura)
2. [Funcionalidades por rol](#2-funcionalidades-por-rol)
3. [Machine Learning](#3-machine-learning)
4. [Sistema multiagente y LLM](#4-sistema-multiagente-y-llm)
5. [Estructura del proyecto](#5-estructura-del-proyecto)
6. [Instalación local](#6-instalación-local)
7. [Variables de entorno](#7-variables-de-entorno)
8. [Despliegue](#8-despliegue)
9. [API](#9-api)
10. [Base de datos](#10-base-de-datos)
11. [Seguridad](#11-seguridad)
12. [Limitaciones conocidas](#12-limitaciones-conocidas)

---

## 1. Arquitectura

```
                       ┌──────────────────────────────┐
  Navegador ─────────▶ │ Render: Flask + gunicorn     │ ──▶ PostgreSQL (Aiven)
  (tienda, admin,      │ app.py · backend/ · frontend/ │
   repartidor)         └──────┬──────────────┬────────┘
                              │              │
                 predicción   │              │  agentes y asistentes
                              ▼              ▼
              ┌──────────────────────┐   OpenAI (gpt-5-mini)
              │ Cloud Run: kimbos-ml │
              │ API de predicción    │◀── Cloud Storage: modelo, métricas,
              └──────────┬───────────┘    dataset DoorDash
                         │ lanza
              ┌──────────▼───────────────────┐
              │ Cloud Run Job: entrenamiento │  (al entregar un pedido
              └──────────────────────────────┘   o desde el dashboard)

  Cloud Scheduler ── 23:00 ──▶ POST /api/automatizacion/reporte-diario
                  ── cada 10 min (10:00-21:59) ──▶ GET /api/health
```

- **Render** sirve la web y la API. El servidor no carga el modelo: le
  pide la predicción a la API de ML (`ML_API_URL`).
- **Google Cloud** entrena y sirve el modelo, guarda sus archivos y
  programa las tareas automáticas.
- **PostgreSQL (Aiven)** guarda usuarios, pedidos, predicciones,
  alertas de los agentes, reportes y el consumo del LLM.

---

## 2. Funcionalidades por rol

| Rol | Qué puede hacer |
|---|---|
| **Cliente** (`/`) | Registrarse, ver el catálogo, armar el carrito, elegir la dirección en el mapa (radio de reparto de 10 km), pagar en efectivo, Yape o Plin, ver el tiempo estimado (preparación + ruta + espera de repartidor), seguir sus pedidos (se actualizan cada 5 s), cancelar mientras el pedido está "Recibido" y consultar al asistente con IA. |
| **Administrador / Operador** (`/admin`) | Gestionar los pedidos en 4 pasos (Recibidos → En preparación → En camino → Entregados) ordenados para el despacho, asignar repartidores, confirmar pagos, ver el dashboard en vivo, el Dashboard ML, los agentes de IA (preguntas y reporte diario), el catálogo, los repartidores, los clientes registrados y el personal (solo ADMIN), y usar el asistente con IA. |
| **Repartidor** (`/repartidor`) | Activar su turno, ver sus pedidos (el más urgente primero) con la llegada estimada y el plazo, abrir la ruta en Google Maps y marcar la entrega. |

Otras reglas del negocio:
- **Horario de atención:** 11:00 a 22:00 (hora de Lima); fuera de ese
  horario no se aceptan pedidos.
- **Inactividad:** la sesión de clientes y repartidores se cierra tras
  10 minutos sin uso.

---

## 3. Machine Learning

**Problema:** clasificación binaria. Predecir, al crear el pedido, si
llegará **retrasado**.

### Datos

| Fuente | Registros | Uso |
|---|---|---|
| DoorDash ETA Prediction (Kaggle, `historical_data.csv`): entregas reales oct. 2014 - feb. 2015 | 176,097 (de 197,428, tras la limpieza) | Entrenamiento |
| Pedidos reales de Kimbos entregados (`fuente_datos = 'REAL'`) | crecen con el uso | Entrenamiento y evaluación |
| Pedidos sintéticos (`SINTETICO_ML`) | 1,000 | **No se usan** (versión descartada v1.0) |

**Regla de retraso:** un pedido está retrasado si su duración real
supera lo estimado en más de 5 minutos. En DoorDash, lo estimado es
ruta + envío al restaurante + preparación típica (29.9 min). En Kimbos,
es ruta + preparación estimada.

**Variables** ([ml/variables.py](ml/variables.py)), calculadas igual al
entrenar y al predecir:

| Variable | Origen en Kimbos |
|---|---|
| `duracion_estimada_min` | Ruta de Google Maps desde la sede |
| `cantidad_items` | Productos del carrito |
| `hora_pedido`, `dia_semana` | Hora de Lima |
| `hora_pico` | 12-14 h y 19-21 h |
| `fin_semana` | Viernes, sábado y domingo |
| `carga_repartidor` | Pedidos activos ÷ repartidores en turno |

### Cinco modelos: 4 manuales y 1 automático

[ml/entrenar_modelo.py](ml/entrenar_modelo.py) compara 5 modelos con
validación cruzada estratificada de 5 pliegues sobre el 80 % de
entrenamiento. El 20 % de prueba solo confirma el resultado.

| Modelo | Tipo | Por qué |
|---|---|---|
| Regresión Logística | Manual | Línea base, simple e interpretable |
| Árbol de Decisión | Manual | Reglas "si... entonces", relaciones no lineales |
| Random Forest | Manual | Robusto al ruido de DoorDash |
| Gradient Boosting | Manual | Suele ser el más preciso en datos tabulares |
| **Gradient Boosting Automático** | **Automático** | `RandomizedSearchCV` busca sus hiperparámetros (8 combinaciones, CV de 3 pliegues) |

- **Criterio de selección:** mayor F1 promedio de validación cruzada.
  F1 equilibra precisión y recall: interesa detectar los retrasos sin
  llenar de falsas alarmas.
- **Todos** usan `class_weight="balanced"`, porque hay menos pedidos
  retrasados que a tiempo.
- **Modelo vigente (v13.0):** Gradient Boosting Automático, F1 CV
  0.607 y ROC-AUC 0.749. El Dashboard ML muestra la comparación
  completa y la justificación de cada modelo.

### Reentrenamiento

- **Automático:** al entregarse un pedido real se lanza el Cloud Run Job.
  Solo entrena si hay pedidos reales nuevos.
- **Manual:** el botón "Reentrenar y comparar 5 modelos" del Dashboard
  ML entrena siempre.
- **Promoción:** la versión nueva **reemplaza a la vigente solo si
  mejora el F1 de CV**; si no, se guarda en el historial como "no
  promovida". La comparación de los 5 modelos se guarda en cada
  entrenamiento (`ml/metrics/comparacion_modelos.json`).

### Uso de la predicción en el sistema

- **Al crear el pedido:** se guarda la probabilidad de retraso. Si
  supera `ALERTA_UMBRAL_RIESGO` (0.4), se activa el sistema multiagente
  de alertas.
- **Dashboard ML:** muestra si el modelo acertó en cada pedido real
  entregado.
- **Estimación de espera de repartidor:** es una simulación separada
  del ML ([backend/repartidores.py](backend/repartidores.py)). Asigna
  los repartidores en el orden en que la comida de cada pedido queda
  lista, y usa ese mismo orden en el panel del admin para despachar.

---

## 4. Sistema multiagente y LLM

Motor común: [backend/llm_agente.py](backend/llm_agente.py) (OpenAI
Responses API, function calling, salidas JSON con esquema estricto).
Cada llamada se registra en la tabla `llm_uso` con su costo.

### A) Alerta de pedido en riesgo (por evento)

Se dispara al crear un pedido con riesgo ≥ 40 %, o con el botón
"Analizar con agentes". Corre en segundo plano y el cliente no espera.
Trabajan 3 agentes en cadena (3 llamadas al LLM, ≈ USD 0.0009 por alerta):

```
🔍 Analista (causa del riesgo; puede consultar la carga y simular con el ML)
   → ⚙️ Operaciones (acción recomendada y minutos extra)
   → 💬 Comunicador (aviso al cliente y resumen al admin)
```

El Comunicador siempre avisa al cliente: si hay demora, le indica los
minutos aproximados; si el pedido va bien, le confirma que llega según
lo previsto.

### B) Reporte diario (por horario, 23:00): 5 agentes

Es el flujo completo con **1 Orquestador, 3 agentes de automatización y
1 Evaluador**. Seis pasos secuenciales. El panel los muestra con un stepper y el
servidor rechaza un paso fuera de orden.

```
0 Datos (SQL, sin IA) → 1 🧭 Orquestador → 2 🔍 Analista de datos
→ 3 🎯 Estratega → 4 ✍️ Redactor → 5 ⭐ Evaluador + decisión del Orquestador
```

El resultado es un **informe operativo**:
- Resumen ejecutivo y 5 cifras clave.
- "Lo que funcionó" y "A vigilar".
- Prioridad de mañana y plan de acción con responsable, horario y meta.
- **Resumen sintético del día:** ticket promedio, diferencia de caja,
  tasa de cancelación y costo de merma y empaques.
- Anexo de control de calidad (plan del Orquestador y notas del
  Evaluador).
- Se puede exportar a PDF.

### C) Consulta a los agentes (por pregunta del administrador): 5 agentes

En "🧠 Agentes de IA → Preguntar a los agentes", el administrador
escribe una pregunta ("¿cómo nos fue esta semana con los retrasos?",
"¿cuántos repartidores necesito mañana?") y trabajan los mismos 5
agentes, orientados a responderla
([backend/agente_consultas.py](backend/agente_consultas.py)):

```
0 🧭 Orquestador (entiende la pregunta, elige el periodo y reparte encargos)
→ 1 Datos del periodo (SQL) → 2 🔍 Analista → 3 🎯 Estratega
→ 4 ✍️ Redactor (responde la pregunta) → 5 ⭐ Evaluador + decisión del Orquestador
```

- **Periodo:** el Orquestador interpreta "hoy", "ayer", "esta semana",
  "la semana pasada" o "este mes"; el código valida las fechas (hasta
  90 días atrás, nunca en el futuro).
- **Preguntas ajenas al negocio** (fútbol, clima…): solo responde el
  Orquestador y no se gasta en los demás agentes.
- **Límite:** `LLM_CONSULTAS_DIARIAS` consultas por día (20 por
  defecto). Costo medido: ≈ USD 0.006 por consulta.

### Reglas comunes

- **Las cifras las calcula el sistema con SQL; los agentes solo las
  interpretan.**
- **Reintento (reporte diario):** si un agente saca nota menor a 6, el
  Orquestador le devuelve el trabajo con la observación del Evaluador
  (1 reintento) y se vuelve a evaluar. El código valida que la decisión
  cuadre con las notas.
- **Días sin pedidos:** el reporte no llama al LLM (costo 0).
- **Costo medido:** alerta ≈ USD 0.0009; reporte diario ≈ USD 0.005; consulta ≈ USD 0.006.
  Presupuesto mensual de USD 10, con cortes automáticos por tipo de uso
  (`LLM_CORTE_*`).

### Asistentes de chat

Hay un asistente para el **cliente** (menú, estado de sus pedidos,
horario) y otro para el **admin** (pedidos activos por riesgo, estado
del modelo, simulaciones). Ambos usan herramientas
([backend/llm_herramientas.py](backend/llm_herramientas.py)) que
consultan la base de datos; el modelo no inventa datos.

---

## 5. Estructura del proyecto

```
app.py                     Aplicación Flask: blueprints, páginas y migraciones al arrancar
db.py                      Pool de conexiones (una conexión por petición; se renueva si se traba)
backend/
  auth.py                  Registro, login (bloqueo tras 5 intentos), /me, cambio de contraseña
  decorators.py            JWT y roles
  horario.py               Horario de atención
  repartidores.py          Turnos y estimación de espera de repartidor
  ml_service.py            Cliente de la API de ML (o modelo local en desarrollo)
  ml_reentrenamiento.py    Reentrenamiento local y estado
  llm_agente.py            Motor de agentes (OpenAI) y control de presupuesto
  llm_herramientas.py      Herramientas que usan los agentes
  agentes_automaticos.py   Multiagente A: alerta de pedido en riesgo
  agente_reporte.py        Multiagente B: reporte diario
  agente_consultas.py      Multiagente C: preguntas del administrador
  routes/                  Endpoints (pedidos, catálogo, sedes, dashboard, automatización, ...)
frontend/
  templates/               index (tienda), admin, repartidor, acceso
  static/js, static/css    Lógica y estilos de cada página
ml/
  variables.py             Variables del modelo (únicas para entrenar y predecir)
  exportar_dataset.py      DoorDash + pedidos reales -> pedidos_ml.csv
  entrenar_modelo.py       5 modelos, selección, promoción y métricas
  job_entrenamiento.py     Cloud Run Job
  servicio.py              API de ML (Cloud Run): /predecir, /metricas, /reentrenar, /salud
  almacen.py               Cloud Storage o carpetas locales
sql/                       Esquema y migraciones
scripts/                   Despliegue en Google Cloud y utilidades
render.yaml                Configuración de Render (Blueprint)
Dockerfile                 Imagen de la API de ML y del job de entrenamiento
```

---

## 6. Instalación local

Requisitos: Python 3.10, una base PostgreSQL y (opcional) claves de
Google Maps y OpenAI.

```powershell
git clone <repositorio>
cd delivery
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env      # completar DATABASE_URL, JWT_SECRET_KEY, MAPS_API_KEY, ...
```

Crear la base (una sola vez, en este orden):

```powershell
python ejecutar_schema.py                          # tablas base y estados
python ejecutar_sedes.py                           # sedes
python ejecutar_catalogo.py                        # categorías, productos y detalle de pedido
python scripts\ejecutar_adaptacion_ml.py           # columnas del ML en pedidos
python scripts\ejecutar_adaptacion_predicciones_ml.py
python scripts\ejecutar_adaptacion_carga.py
python crear_sede.py                               # datos de la tienda y la sede
python crear_admin.py                              # primer administrador
```

Las demás tablas y columnas (alertas, reportes, consumo del LLM, pagos,
cancelación, turnos) se crean solas al arrancar la app o en el primer
uso.

Ejecutar:

```powershell
python app.py               # http://127.0.0.1:5000
```

Sin `ML_API_URL`, el servidor usa el modelo local
`ml/models/modelo_final.joblib`. Para entrenar en local hace falta el
dataset de DoorDash en `ml/data/externo/historical_data.csv`:

```powershell
pip install -r requirements-ml.txt
python ml/reentrenar.py
```

---

## 7. Variables de entorno

Ver [.env.example](.env.example). Los secretos **no** se suben al
repositorio.

| Variable | Para qué |
|---|---|
| `DATABASE_URL` | Conexión a PostgreSQL |
| `JWT_SECRET_KEY` | Firma de las sesiones |
| `MAPS_API_KEY` | Google Maps (mapa, rutas y distancias) |
| `ML_API_URL`, `ML_API_KEY` | API de ML en Cloud Run (vacío = modelo local) |
| `REPARTIDORES_DISPONIBLES` | Respaldo si no hay repartidores en turno registrados |
| `REENTRENAMIENTO_AUTOMATICO` | Reentrenar al entregar pedidos (`true`/`false`) |
| `OPENAI_API_KEY`, `LLM_MODELO` | Agentes y asistentes (vacío = apagados) |
| `LLM_PRESUPUESTO_USD`, `LLM_CORTE_ADMIN_USD`, `LLM_CORTE_CLIENTE_USD`, `LLM_CORTE_AUTOMATIZACION_USD` | Presupuesto mensual y cortes por tipo de uso |
| `LLM_MENSAJES_DIARIOS_CLIENTE`, `LLM_MENSAJES_DIARIOS_ADMIN` | Límite de mensajes por usuario y día |
| `ALERTA_UMBRAL_RIESGO` | Riesgo mínimo para activar la alerta multiagente (0.4) |
| `AUTOMATIZACION_KEY` | Clave que envía Cloud Scheduler para el reporte diario |
| `TIENDA_APERTURA`, `TIENDA_CIERRE` | Horario de atención (hora de Lima) |
| `RADIO_COBERTURA_KM` | Radio máximo de reparto |
| `COSTO_EMPAQUE_PEDIDO` | Costo de empaque por pedido (S/) para el reporte diario |
| `LLM_CONSULTAS_DIARIAS` | Máximo de preguntas a los agentes por día (20) |
| `CORS_ORIGENES` | Orígenes permitidos para llamar a la API desde otro dominio |

---

## 8. Despliegue

**Render (web y API):** se despliega solo con cada `git push` a `main`
([render.yaml](render.yaml)). Comando de arranque:
`gunicorn app:app --workers 1 --threads 8 --timeout 120`.

**Google Cloud (ML y tareas programadas):**

```powershell
# API de ML, job de entrenamiento, bucket y secretos
powershell -ExecutionPolicy Bypass -File scripts\desplegar_ml_gcp.ps1
# Solo publicar cambios de código del ML
powershell -ExecutionPolicy Bypass -File scripts\desplegar_ml_gcp.ps1 -SoloCodigo

# Reporte diario a las 23:00 (Cloud Scheduler)
powershell -ExecutionPolicy Bypass -File scripts\programar_reporte_gcp.ps1
# Mantener despierto el servidor de Render (y la API de ML) en horario de atención
powershell -ExecutionPolicy Bypass -File scripts\mantener_activo_gcp.ps1
```

---

## 9. API

Todas las rutas `/api` responden JSON (también en errores 404, 405 y
500). Autenticación: `Authorization: Bearer <token>`.

| Módulo | Rutas principales |
|---|---|
| Autenticación | `POST /api/auth/registro`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/cambiar-password` |
| Catálogo y sede | `GET /api/catalogo`, `GET /api/sedes/activa`, gestión de productos y categorías (admin) |
| Pedidos (cliente) | `POST /api/pedidos`, `GET /api/pedidos/mis-pedidos`, `POST /api/pedidos/<id>/cancelar`, `POST /api/pedidos/<id>/pago/operacion`, `GET /api/pedidos/espera-estimada` |
| Pedidos (admin) | `GET /api/pedidos?estados=&limite=&desde=`, `GET /api/pedidos/conteo`, `PATCH /api/pedidos/<id>/estado`, `POST /api/pedidos/<id>/pago/confirmar` |
| Repartidores | `GET/POST /api/repartidores`, `PATCH /api/repartidores/<id>`, panel: `/api/repartidor/perfil`, `/turno`, `/pedidos`, `/pedidos/<id>/entregado` |
| Dashboard y ML | `GET /api/dashboard?periodo=1|7|30`, `GET /api/pedidos/ml/resumen`, `POST /api/pedidos/ml/reentrenar` |
| Agentes | `POST /api/automatizacion/pedidos/<id>/alerta`, `POST /api/automatizacion/reportes/pasos/<paso>`, `GET /api/automatizacion/reportes`, `POST /api/automatizacion/reporte-diario` (Cloud Scheduler), `POST/GET /api/automatizacion/consultas`, `POST /api/automatizacion/consultas/<id>/pasos/<paso>` |
| Asistentes | `POST /api/asistente/cliente`, `POST /api/asistente/admin`, `GET /api/asistente/estado` |
| Personal y clientes | `GET/POST /api/personal`, `PATCH /api/personal/<id>`, `GET /api/personal/clientes` (solo ADMIN) |
| Salud | `GET /api/health` |

---

## 10. Base de datos

| Tabla | Contenido |
|---|---|
| `usuarios`, `repartidores` | Cuentas por rol (CLIENTE, ADMIN, OPERADOR, REPARTIDOR) y datos del repartidor (vehículo, turno) |
| `sedes`, `categorias_producto`, `productos` | Tienda y catálogo |
| `pedidos`, `detalle_pedido`, `historial_pedido`, `estados_pedido` | Pedidos, productos, cambios de estado (pago, cancelación, recojo y entrega) |
| `predicciones_ml` | Predicción de cada pedido con las variables usadas |
| `alertas_pedido` | Resultado del multiagente A (causa, acción, aviso al cliente y resumen) |
| `reportes_diarios` | Resultado del multiagente B por día |
| `consultas_agentes` | Preguntas del administrador y la respuesta de los 5 agentes |
| `llm_uso` | Tokens, costo y duración de cada llamada al LLM |

---

## 11. Seguridad

- **Contraseñas:** guardadas con hash (`werkzeug`), mínimo 8 caracteres.
- **Sesiones:** JWT de 4 horas, con permisos por rol en cada ruta.
- **Login:** bloqueo de 1 minuto tras 5 intentos fallidos (por correo
  y por IP), con mensajes genéricos.
- **CORS:** restringido (`CORS_ORIGENES`).
- **Validación en el servidor:** distancia de entrega, horario de
  atención y estados de los pedidos.
- **Secretos:** solo en variables de entorno, Render y Secret Manager;
  `.env` está en `.gitignore`.
- **Tareas programadas:** la llamada de Cloud Scheduler se valida con
  `X-Automatizacion-Key`.

---

## 12. Limitaciones conocidas

- **Base de datos:** Aiven (plan gratis) se apaga sin uso. El pool de
  conexiones se renueva solo cuando vuelve.
- **Servidor web:** Render (plan gratis) se duerme sin tráfico. Cloud
  Scheduler lo mantiene despierto en horario de atención.
- **Pocos datos reales:** el modelo se apoya en DoorDash, y las
  métricas en pedidos reales de Kimbos aún tienen poca muestra.
- **Costo de merma y empaques:** el empaque es un costo estimado
  (`COSTO_EMPAQUE_PEDIDO`), porque la base no guarda costos de
  productos.
- **Pagos con Yape o Plin:** se confirman manualmente desde el panel
  (no hay integración con la pasarela).

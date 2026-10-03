# Documento de Traspaso del Proyecto — Kimbos Delivery

> Versión actualizada al **03/10/2026**. Reemplaza al documento anterior, que
> describía un modelo entrenado con datos sintéticos (ya descartado).

## 1. Objetivo del sistema

**Nombre:** Implementación de un Sistema Web de Gestión y Seguimiento de
Pedidos Delivery con Predicción de Retrasos mediante Machine Learning.

Kimbos (caso académico, Cerro de Pasco – Perú) gestiona pedidos delivery,
catálogo, usuarios y estados. Usa Google Maps para ubicación, distancia y ruta,
PostgreSQL como base de datos y Machine Learning para predecir si un pedido
tiene riesgo de retrasarse.

Flujo principal:

Cliente → catálogo → carrito → ubicación → ruta → confirmación → pedido →
**predicción ML** → preparación → en ruta → entrega → **resultado real** →
comparación → **reentrenamiento automático**.

---

## 2. Arquitectura y decisiones técnicas

### Tecnologías

- Backend: Python 3.10 + Flask (REST), `.venv`.
- Base de datos: PostgreSQL en Aiven (`delivery_db`).
- Frontend: HTML, CSS, JavaScript y Bootstrap.
- Mapas: Google Maps JavaScript API, Places API (New), Routes API.
- Autenticación: JWT. Roles: CLIENTE, OPERADOR, ADMIN, REPARTIDOR.
- ML: pandas, NumPy, scikit-learn, joblib, matplotlib.
- Repositorio: GitHub (rama `main`).

### Reglas de negocio

- Estados: `REGISTRADO → PREPARANDO → EN_RUTA → ENTREGADO`.
- Delivery: `S/ 3.00 + S/ 1.20 × distancia_km` (calculado en el backend).
- Precios de productos: siempre desde PostgreSQL.
- Al pasar a ENTREGADO se calculan `duracion_real_min` y
  `retraso = duración real > tiempo_estimado_total_min + 5 min`.

### Tablas principales

`usuarios`, `repartidores`, `estados_pedido`, `pedidos`, `historial_pedido`,
`clima_pedido`, `predicciones_ml`, `auditoria`, `sedes`,
`categorias_producto`, `productos`, `detalle_pedido`.

`pedidos.fuente_datos` distingue `REAL` de `SINTETICO_ML`.

### Arquitectura ML

```text
DoorDash (Kaggle, CSV local)  +  PostgreSQL (pedidos reales entregados)
                 \                 /
              ml/exportar_dataset.py   (limpieza + regla de retraso)
                        ↓
              ml/data/pedidos_ml.csv   (no se sube a Git)
                        ↓
              ml/entrenar_modelo.py    (3 modelos, CV, versión, promoción)
                        ↓
              ml/models/modelo_final.joblib  +  ml/metrics/*
                        ↓
              backend/ml_service.py    (predicción; recarga si cambia el archivo)
                        ↓
              pedido nuevo → predicción → tabla predicciones_ml
```

`ml/variables.py` define una sola vez las variables y reglas (hora pico, fin de
semana, carga). Lo usan la exportación, el entrenamiento y Flask.

---

## 3. Reglas de comportamiento para la IA que continúe

- Responder en español; ser directa y práctica; una etapa a la vez.
- Dar comandos exactos de PowerShell cuando corresponda.
- **No inventar datos, métricas ni resultados**: leer `ml/metrics/metricas.json`.
- Revisar el resultado de cada paso antes de continuar.
- Corregir al usuario cuando haya un error; no dar la razón automáticamente.
- Explicar conceptos de forma sencilla para una exposición universitaria.

### Código

1. Identificar el archivo y revisar el código existente.
2. Hacer el cambio mínimo necesario (no reemplazar archivos completos sin motivo).
3. Ejecutar una comprobación y verificar el resultado.

### Seguridad

No pedir contraseñas, `DATABASE_URL`, `JWT_SECRET_KEY`, `MAPS_API_KEY` ni
tokens. El `.env` está ignorado por Git y no debe subirse.

### Decisiones del docente (no revertir)

- **El docente no acepta datos sintéticos.** Los 1,000 registros
  `SINTETICO_ML` siguen en la BD solo como respaldo: **no se muestran en el
  panel ni se usan para entrenar**.
- El modelo se entrena con **datos reales**: dataset público DoorDash +
  pedidos reales de Kimbos.
- El modelo **se mejora con los registros nuevos**: reentrenamiento automático
  al entregar cada pedido (ver §4).

---

## 4. Estado exacto de avance

### Sistema base — completo

Flask, frontend cliente, panel admin, registro/login, JWT, roles, catálogo,
gestión de productos y categorías, pedidos, cálculo de delivery, Google Maps y
rutas, estados, historial, auditoría, sede activa.

### Datos de entrenamiento

| Fuente | Registros | Detalle |
|---|---|---|
| DoorDash ETA Prediction (Kaggle) | 197,428 → **176,097** tras limpieza | Entregas reales oct. 2014 – feb. 2015 (EE. UU.), con ruido añadido por DoorDash |
| Pedidos reales de Kimbos entregados | **6** (al 03/10/2026) | Tabla `pedidos`, `fuente_datos = REAL` |

- Archivo externo: `ml/data/externo/historical_data.csv` (**no está en Git**;
  descargar de Kaggle buscando "DoorDash ETA Prediction").
- Limpieza: sin nulos en tiempos/carga; ≥ 1 repartidor en turno y ≥ 1 pedido
  pendiente (las filas con 0 repartidores eran inconsistentes y distorsionaban
  el modelo); duración real entre 10 y 180 min; ruta > 0; máximo 30 ítems.
- Zona horaria: DoorDash viene en UTC; se convierte a `America/Los_Angeles`
  (suposición: así los picos caen a las 12 h y 18 h).
- **Regla de retraso**:
  - DoorDash no trae hora prometida → estimado = ruta + envío al restaurante +
    **29.9 min** de preparación típica (mediana del dataset). Retraso si
    real > estimado + 5 min (**37.5 %** de retrasos).
  - Kimbos: real > ruta + preparación estimada + 5 min.
- Todo esto queda registrado en `ml/data/dataset_info.json`.

### Variables del modelo (7)

`duracion_estimada_min`, `cantidad_items`, `hora_pedido`, `dia_semana`,
`hora_pico` (12–14 y 19–21), `fin_semana` (vie–dom), `carga_repartidor`.

- `carga_repartidor = pedidos activos ÷ repartidores disponibles`. Se usa en
  lugar de los pedidos activos sin dividir porque DoorDash tiene ~41 pedidos
  activos y Kimbos 0–3; la carga sí es comparable y es la variable más
  predictiva.
- Kimbos no registra repartidores: se usa `REPARTIDORES_DISPONIBLES` del `.env`
  (por defecto 2).
- `distancia_km` y `tiempo_preparacion_estimado_min` se guardan en
  `predicciones_ml` pero **no** son entradas (DoorDash no las tiene).
- Objetivo: `retraso` (0 = A tiempo, 1 = Retrasado).

### Modelo activo: v4.0 (Gradient Boosting)

Entrenado el 03/10/2026 con 176,103 registros (176,097 DoorDash + 6 Kimbos).
División 80/20 estratificada; validación cruzada estratificada de 5 folds;
selección por mayor F1 promedio de CV. Prueba con 35,221 registros:

| Modelo | F1 CV | Accuracy | Precision | Recall | F1 test | ROC-AUC |
|---|---|---|---|---|---|---|
| Regresión Logística | 0.6027 | 67.6 % | 55.7 % | 66.1 % | 0.6046 | 0.7307 |
| Random Forest | 0.6059 | 70.0 % | 59.5 % | 62.7 % | 0.6105 | 0.7487 |
| **Gradient Boosting** ✓ | **0.6067** | 69.9 % | 59.3 % | 62.8 % | 0.6097 | **0.7490** |

Matriz de confusión (v4.0): `[[16314, 5701], [4915, 8291]]`
(filas = real A tiempo / Retrasado; columnas = predicho).

Notas para la exposición:

- Random Forest y Gradient Boosting están prácticamente empatados.
- La “mejora” de v2.0 (0.6063) a v4.0 (0.6067) es mínima. Con 6 pedidos de
  Kimbos entre 176 mil, **no** se debe afirmar que los pedidos de Kimbos
  mejoraron el modelo. Lo correcto es: *“el sistema reentrena con cada pedido
  entregado y solo cambia de modelo si las métricas mejoran”*.

### Historial de versiones

| Versión | Datos | Resultado |
|---|---|---|
| v1.0 | 1,000 sintéticos | **Descartado** (archivado en `archivo_sintetico/`) |
| v2.0 | DoorDash + 4 Kimbos | Activo hasta v4.0 (Random Forest, F1 CV 0.6063) |
| v3.0 | DoorDash + 5 Kimbos | No mejoró (0.6062), no se activó |
| v4.0 | DoorDash + 6 Kimbos | **Activo** (Gradient Boosting, F1 CV 0.6067) |

### Reentrenamiento

- **Automático**: al marcar un pedido como ENTREGADO se reentrena en segundo
  plano (`backend/ml_reentrenamiento.py`). Se controla con
  `REENTRENAMIENTO_AUTOMATICO` en `.env` (activo por defecto).
- **Manual**: botón en el dashboard (solo ADMIN) o por consola
  `python ml/reentrenar.py`.
- Solo se reentrena si hay pedidos reales nuevos desde el último entrenamiento.
- La nueva versión **solo reemplaza a la activa si su F1 CV es igual o mayor**;
  si no, queda en el historial como “No mejoró”.
- Un único reentrenamiento a la vez (bloqueo por archivo,
  `ml/metrics/.reentrenando.lock`). Si se entregan varios pedidos durante un
  entrenamiento, al terminar se vuelve a entrenar una vez con todos.
- El modelo se escribe de forma atómica y Flask lo recarga sin reiniciar.
- La versión anterior se archiva como `ml/models/modelo_vN.joblib` (no se sube
  a Git). Desde Flask se entrena con 1 proceso (`ML_N_JOBS=1`), ~50–60 s.

### Panel administrativo

- Lista solo pedidos reales. Cada tarjeta muestra predicción (clase, % de
  riesgo, versión) y, tras la entrega, el resultado real y si coincidió.
- **Dashboard ML** (botón “🤖 Dashboard ML”):
  1. *Evaluación del modelo*: métricas, matriz de confusión, comparación de
     modelos, fuente del dataset y regla de retraso.
  2. *Predicciones en pedidos reales*: tabla pedido por pedido (predicción vs.
     resultado real, ✓ Acertó / ✕ Falló / Pendiente). La matriz y
     Precision/Recall/F1 de pedidos reales aparecen desde 30 evaluados.
     Excluye predicciones del modelo sintético v1.0.
  3. *Evolución del modelo*: estado del reentrenamiento (en curso / último
     resultado), botón de reentrenar y las 10 versiones más recientes.

### Pedidos reales registrados (al 03/10/2026)

| Pedido | Modelo | Predicción | Resultado real | ¿Coincidió? |
|---|---|---|---|---|
| PED-2026-2257729A | — (antes de ML) | — | Retrasado (91 / 28 min) | — |
| PED-2026-58BE97D3 | v1.0 (descartado) | A tiempo 34.0 % | Retrasado (38 / 21 min) | No |
| PED-2026-77241475 | v1.0 (descartado) | A tiempo 45.7 % | A tiempo (8 / 31 min) | Sí |
| PED-2026-80DB7A68 | v1.0 (descartado) | A tiempo 40.3 % | A tiempo (17 / 25 min) | Sí |
| PED-2026-F38B42EC | v2.0 | A tiempo 23.3 % | A tiempo (17 / 20 min) | Sí |
| PED-2026-A3571590 | v2.0 | A tiempo 23.6 % | A tiempo (6 / 18 min) | Sí |

En el dashboard cuentan solo los 2 de v2.0 en adelante. Ojo: varios tiempos
(8, 6, 91 min) vienen de pruebas en las que el estado no se cambió en el
momento real; esos registros también entran al reentrenamiento.

### Base de datos — migraciones aplicadas

- `sql/adaptar_ml_pedidos.sql`, `sql/adaptar_predicciones_ml.sql`.
- `sql/adaptar_predicciones_carga.sql`: añade `repartidores_disponibles` y
  convierte `carga_repartidor` a `NUMERIC(8, 4)` en `predicciones_ml`
  (ejecutado con `python -m scripts.ejecutar_adaptacion_carga`).

### Endpoints

| Método | Ruta | Rol |
|---|---|---|
| POST | `/api/auth/registro`, `/api/auth/login` | público |
| GET | `/api/auth/me` | autenticado |
| GET | `/api/sedes/activa` | — |
| GET / POST / PATCH | `/api/catalogo…` | lectura pública; escritura ADMIN (disponibilidad: ADMIN, OPERADOR) |
| POST | `/api/pedidos` | CLIENTE, ADMIN, OPERADOR (incluye predicción ML) |
| GET | `/api/pedidos/mis-pedidos` | autenticado |
| GET | `/api/pedidos` | ADMIN, OPERADOR (solo reales) |
| PATCH | `/api/pedidos/<id>/estado` | ADMIN, OPERADOR (ENTREGADO dispara reentrenamiento) |
| GET | `/api/pedidos/ml/resumen` | ADMIN, OPERADOR |
| POST | `/api/pedidos/ml/reentrenar` | ADMIN |

---

## 5. Problemas conocidos

1. **Memoria del equipo de desarrollo.** El archivo de paginación está en 2 GB
   (límite de memoria virtual 17.8 GB). Con Chrome, VS Code, SQL Server y MySQL
   abiertos, el reentrenamiento falla con `MemoryError` o “El archivo de
   paginación es demasiado pequeño”. Solución: archivo de paginación
   personalizado en D: (8192 / 16384 MB) y reiniciar; o detener SQL Server y
   MySQL (Kimbos no los usa).
2. **Latencia:** cada petición tarda ~5 s porque abre dos conexiones nuevas a
   Aiven (token + consulta). Mejora pendiente: pool de conexiones.
3. **Git y el modelo:** cada reentrenamiento modifica `modelo_final.joblib`
   (7.5 MB, comprimido), métricas e historial. Hacer commit del modelo solo en
   momentos clave (antes de presentar o desplegar).
4. Con `debug=True`, Flask carga la app dos veces (~580 MB cada proceso).

---

## 6. Siguientes pasos pendientes

1. **Subir a GitHub**: `git push origin main` (hay commits locales sin subir).
2. **Acumular pedidos reales** cambiando los estados en el momento real, para
   que la sección 2 del dashboard llegue a 30 evaluados y muestre la matriz.
3. **Despliegue en Render** (preparado: `render.yaml` + `.python-version`):
   - Plan free (512 MB). Flask + modelo usa ~140 MB. Gunicorn con 1 worker y
     4 hilos. Python fijado en 3.10 (el predeterminado de Render, 3.14, no es
     compatible con numpy/scipy fijados).
   - **Render solo predice.** No tiene el CSV de DoorDash ni disco
     persistente: el dashboard oculta el botón de reentrenar y
     `REENTRENAMIENTO_AUTOMATICO=false`.
   - **Flujo para actualizar el modelo:** reentrenar en el equipo de
     desarrollo (usa los pedidos de producción, que están en la misma BD de
     Aiven) → `git commit` del modelo y métricas → `git push` → Render
     redespliega solo.
   - Secretos en el panel de Render: `DATABASE_URL`, `MAPS_API_KEY`
     (`JWT_SECRET_KEY` lo genera Render).
   - Google Maps se usa solo en el navegador: añadir el dominio
     `*.onrender.com` a las restricciones de la API Key.
   - El plan free se duerme tras 15 min sin visitas (30–60 s en despertar):
     abrir el sitio unos minutos antes de presentar.
   - Probar `/`, `/admin`, `/api/health` y una predicción en producción.
4. Opcional: pool de conexiones a PostgreSQL; rellenar nombre y teléfono del
   destinatario con los datos del cliente que inició sesión.

---

## 7. Cómo ejecutar

```powershell
cd C:\Proyectos\delivery
.\.venv\Scripts\Activate.ps1
python app.py
```

Variables del `.env` (ver `.env.example`): `DATABASE_URL`, `JWT_SECRET_KEY`,
`MAPS_API_KEY`, `ML_API_URL`, `REPARTIDORES_DISPONIBLES`,
`REENTRENAMIENTO_AUTOMATICO`.

Comandos ML (desde la raíz, con el `.venv` activo):

```powershell
python ml/reentrenar.py      # exportar + entrenar (código 0 activado, 2 sin datos nuevos, 3 no mejoró)
python ml/probar_modelo.py   # prueba rápida del modelo activo
python -m scripts.verificar_ultima_prediccion
```

---

## 8. Archivos importantes

```text
app.py, db.py
backend/
├── auth.py, decorators.py
├── ml_service.py            predicción y recarga del modelo
├── ml_reentrenamiento.py    reentrenamiento manual/automático, bloqueo, estado
└── routes/ pedidos.py, sedes.py, catalogo.py
frontend/
├── templates/ index.html, admin.html
└── static/ css/{cliente,admin}.css, js/{cliente,admin}.js
ml/
├── variables.py             variables y reglas comunes
├── exportar_dataset.py      DoorDash + Kimbos → pedidos_ml.csv
├── entrenar_modelo.py       entrenamiento, versión, promoción
├── reentrenar.py            exportar + entrenar
├── probar_modelo.py
├── data/ dataset_info.json, externo/historical_data.csv (no en Git)
├── models/ modelo_final.joblib, archivo_sintetico/
├── metrics/ metricas.json, comparacion_modelos.csv, matriz_confusion.png,
│            historial_modelos.json, archivo_sintetico/
└── archivo_sintetico/       generadores de datos sintéticos (no se usan)
scripts/                     verificaciones y migraciones (python -m scripts.<nombre>)
sql/                         esquema y migraciones
docs/Documento_traspaso_Kimbos_ML.md
```

---

## Instrucción final para la IA que reciba este documento

**No comenzar el proyecto desde cero ni volver a datos sintéticos.**

El sistema ya tiene Flask, PostgreSQL, frontend, panel, Google Maps, modelo
v4.0 entrenado con datos reales (DoorDash + Kimbos), predicción en cada pedido,
comparación con el resultado real, dashboard ML y reentrenamiento automático.

Continuar con: subir a GitHub, acumular pedidos reales y preparar el despliegue.
Antes de citar cualquier métrica, leer `ml/metrics/metricas.json` e
`ml/metrics/historial_modelos.json`, porque cambian con cada reentrenamiento.

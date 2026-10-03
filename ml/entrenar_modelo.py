import json
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime, timezone

import joblib
import matplotlib.pyplot as plt
import pandas as pd

from sklearn.ensemble import (
    RandomForestClassifier,
    HistGradientBoostingClassifier
)

from sklearn.linear_model import LogisticRegression

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    ConfusionMatrixDisplay
)

from sklearn.model_selection import (
    train_test_split,
    StratifiedKFold,
    cross_val_score
)

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


# =========================================================
# RUTAS
# =========================================================

RAIZ = Path(__file__).resolve().parent.parent

if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from ml.variables import COLUMNAS_MODELO, TARGET

ARCHIVO_INFO_DATASET = (
    RAIZ
    / "ml"
    / "data"
    / "dataset_info.json"
)

ARCHIVO_DATASET = (
    RAIZ
    / "ml"
    / "data"
    / "pedidos_ml.csv"
)

CARPETA_MODELOS = (
    RAIZ
    / "ml"
    / "models"
)

CARPETA_METRICAS = (
    RAIZ
    / "ml"
    / "metrics"
)

CARPETA_MODELOS.mkdir(
    parents=True,
    exist_ok=True
)

CARPETA_METRICAS.mkdir(
    parents=True,
    exist_ok=True
)


# =========================================================
# CONFIGURACIÓN
# =========================================================

RANDOM_STATE = 42

# Procesos en paralelo. Con -1 se usa un proceso por nucleo y,
# con ~180 mil registros, puede agotar la memoria del equipo.
N_JOBS = int(os.getenv("ML_N_JOBS", "2"))

# Columnas de entrada y objetivo: ver ml/variables.py


# =========================================================
# MODELO ACTUAL E HISTORIAL DE VERSIONES
# =========================================================

ARCHIVO_MODELO = CARPETA_MODELOS / "modelo_final.joblib"
ARCHIVO_METRICAS = CARPETA_METRICAS / "metricas.json"
ARCHIVO_HISTORIAL = CARPETA_METRICAS / "historial_modelos.json"


def leer_json(ruta, defecto):

    if not ruta.exists():
        return defecto

    return json.loads(
        ruta.read_text(encoding="utf-8")
    )


def resumen_version(metricas, promovido):

    dataset = metricas["dataset"]
    elegido = metricas["resultados"][
        metricas["modelo_seleccionado"]
    ]

    return {
        "version": metricas["version_modelo"],
        "fecha_entrenamiento_utc": metricas["fecha_entrenamiento_utc"],
        "modelo": metricas["modelo_seleccionado"],
        "registros_totales": dataset["registros_totales"],
        "registros_externos": dataset.get("registros_externos", 0),
        "registros_reales": dataset.get("registros_reales", 0),
        "f1_cv": elegido["f1_cv_promedio"],
        "accuracy": elegido["accuracy_test"],
        "precision": elegido["precision_test"],
        "recall": elegido["recall_test"],
        "f1": elegido["f1_test"],
        "roc_auc": elegido["roc_auc_test"],
        "promovido": promovido
    }


metricas_actuales = leer_json(ARCHIVO_METRICAS, None)
historial = leer_json(ARCHIVO_HISTORIAL, [])

# La primera vez, el historial arranca con el modelo vigente.
if not historial and metricas_actuales:
    historial.append(
        resumen_version(metricas_actuales, True)
    )

# v1.0 fue el modelo entrenado con datos sinteticos
# (descartado). Los modelos con datos reales empiezan en v2.0.
numero_version = max(
    [
        int(float(v["version"].lstrip("v")))
        for v in historial
    ],
    default=1
) + 1

version_modelo = f"v{numero_version}.0"


# =========================================================
# CARGAR DATASET
# =========================================================

df = pd.read_csv(
    ARCHIVO_DATASET
)

print("\n========================================")
print("ENTRENAMIENTO MACHINE LEARNING - KIMBOS")
print("========================================")

print(
    "Registros:",
    len(df)
)

print(
    "Variables de entrada:",
    len(COLUMNAS_MODELO)
)

registros_reales = int(
    (df["fuente_datos"] == "REAL").sum()
)

# Externos = dataset publico DoorDash.
registros_externos = int(
    len(df) - registros_reales
)

print(
    "DoorDash:",
    registros_externos,
    "| Reales Kimbos:",
    registros_reales
)


# Sin pedidos reales nuevos desde el ultimo entrenamiento
# (promovido o no) el dataset seria el mismo: no se reentrena.
if historial:

    reales_ultimo = max(
        v["registros_reales"]
        for v in historial
    )

    if registros_reales <= reales_ultimo:

        print(
            "\nNo hay pedidos reales nuevos desde "
            f"el ultimo entrenamiento ({reales_ultimo} reales). "
            "No se reentrena."
        )

        sys.exit(2)


# =========================================================
# VALIDAR
# =========================================================

columnas_necesarias = (
    COLUMNAS_MODELO
    + [TARGET]
)

faltantes = [
    columna
    for columna in columnas_necesarias
    if columna not in df.columns
]

if faltantes:

    raise ValueError(
        f"Faltan columnas: {faltantes}"
    )


if df[columnas_necesarias].isnull().any().any():

    raise ValueError(
        "Existen valores nulos en "
        "las variables de entrenamiento."
    )


# =========================================================
# X / Y
# =========================================================

X = df[COLUMNAS_MODELO].copy()

y = df[TARGET].astype(int)


print("\n=== DISTRIBUCION ===")

print(
    y.value_counts()
    .sort_index()
)


# =========================================================
# TRAIN / TEST
# 80 % entrenamiento
# 20 % prueba
# =========================================================

(
    X_train,
    X_test,
    y_train,
    y_test
) = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=RANDOM_STATE,
    stratify=y
)


print("\n=== DIVISION DE DATOS ===")

print(
    "Entrenamiento:",
    len(X_train)
)

print(
    "Prueba:",
    len(X_test)
)


# =========================================================
# MODELOS
# =========================================================

modelos = {

    "Regresion Logistica": Pipeline([
        (
            "escalado",
            StandardScaler()
        ),
        (
            "modelo",
            LogisticRegression(
                max_iter=2000,
                class_weight="balanced",
                random_state=RANDOM_STATE
            )
        )
    ]),

    "Random Forest": RandomForestClassifier(
        n_estimators=150,
        max_depth=10,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=N_JOBS
    ),

    # Version de Gradient Boosting optimizada para
    # datasets grandes (~180 mil registros).
    "Gradient Boosting": HistGradientBoostingClassifier(
        max_iter=200,
        learning_rate=0.1,
        class_weight="balanced",
        random_state=RANDOM_STATE
    )
}


# =========================================================
# VALIDACIÓN CRUZADA
# =========================================================

cv = StratifiedKFold(
    n_splits=5,
    shuffle=True,
    random_state=RANDOM_STATE
)


resultados = {}

mejor_nombre = None
mejor_f1_cv = -1

mejor_modelo = None


print("\n========================================")
print("COMPARACION DE MODELOS")
print("========================================")


for nombre, modelo in modelos.items():

    print(
        f"\n>>> {nombre}"
    )

    # -----------------------------------------------------
    # VALIDACIÓN CRUZADA SOLO SOBRE TRAIN
    # -----------------------------------------------------

    scores_cv = cross_val_score(
        modelo,
        X_train,
        y_train,
        cv=cv,
        scoring="f1",
        n_jobs=N_JOBS
    )

    f1_cv_promedio = (
        scores_cv.mean()
    )

    f1_cv_std = (
        scores_cv.std()
    )

    # -----------------------------------------------------
    # ENTRENAR
    # -----------------------------------------------------

    modelo.fit(
        X_train,
        y_train
    )

    predicciones = modelo.predict(
        X_test
    )

    probabilidades = (
        modelo.predict_proba(
            X_test
        )[:, 1]
    )

    # -----------------------------------------------------
    # MÉTRICAS TEST
    # -----------------------------------------------------

    accuracy = accuracy_score(
        y_test,
        predicciones
    )

    precision = precision_score(
        y_test,
        predicciones,
        zero_division=0
    )

    recall = recall_score(
        y_test,
        predicciones,
        zero_division=0
    )

    f1 = f1_score(
        y_test,
        predicciones,
        zero_division=0
    )

    roc_auc = roc_auc_score(
        y_test,
        probabilidades
    )

    matriz = confusion_matrix(
        y_test,
        predicciones
    )


    resultados[nombre] = {

        "f1_cv_promedio": float(
            f1_cv_promedio
        ),

        "f1_cv_desviacion": float(
            f1_cv_std
        ),

        "accuracy_test": float(
            accuracy
        ),

        "precision_test": float(
            precision
        ),

        "recall_test": float(
            recall
        ),

        "f1_test": float(
            f1
        ),

        "roc_auc_test": float(
            roc_auc
        ),

        "matriz_confusion": (
            matriz.tolist()
        )
    }


    print(
        f"F1 CV:        "
        f"{f1_cv_promedio:.4f}"
    )

    print(
        f"Accuracy:     "
        f"{accuracy:.4f}"
    )

    print(
        f"Precision:    "
        f"{precision:.4f}"
    )

    print(
        f"Recall:       "
        f"{recall:.4f}"
    )

    print(
        f"F1 Test:      "
        f"{f1:.4f}"
    )

    print(
        f"ROC-AUC:      "
        f"{roc_auc:.4f}"
    )

    print(
        "Matriz:"
    )

    print(
        matriz
    )


    # -----------------------------------------------------
    # SELECCIÓN
    # Se elige por F1 promedio de validación cruzada.
    # No por el test.
    # -----------------------------------------------------

    if f1_cv_promedio > mejor_f1_cv:

        mejor_f1_cv = (
            f1_cv_promedio
        )

        mejor_nombre = nombre

        mejor_modelo = modelo


# =========================================================
# EVALUAR MODELO ELEGIDO
# =========================================================

pred_final = mejor_modelo.predict(
    X_test
)

prob_final = (
    mejor_modelo.predict_proba(
        X_test
    )[:, 1]
)

matriz_final = confusion_matrix(
    y_test,
    pred_final
)


# =========================================================
# ¿EL NUEVO MODELO MEJORA AL VIGENTE?
# Mismo criterio de seleccion: F1 promedio de CV.
# =========================================================

f1_cv_vigente = (
    metricas_actuales["resultados"][
        metricas_actuales["modelo_seleccionado"]
    ]["f1_cv_promedio"]
    if metricas_actuales
    else None
)

promovido = bool(
    f1_cv_vigente is None
    or mejor_f1_cv >= f1_cv_vigente
)


# =========================================================
# GUARDAR MODELO
# =========================================================

fecha_entrenamiento = (
    datetime.now(
        timezone.utc
    ).isoformat()
)


paquete_modelo = {

    "modelo": mejor_modelo,

    "columnas": COLUMNAS_MODELO,

    "target": TARGET,

    "version": version_modelo,

    "nombre_modelo": mejor_nombre,

    "seleccionado_por": (
        "F1 promedio de validacion cruzada"
    ),

    "fecha_entrenamiento_utc": (
        fecha_entrenamiento
    )
}


def guardar_historial():

    elegido = resultados[mejor_nombre]

    historial.append({
        "version": version_modelo,
        "fecha_entrenamiento_utc": fecha_entrenamiento,
        "modelo": mejor_nombre,
        "registros_totales": int(len(df)),
        "registros_externos": registros_externos,
        "registros_reales": registros_reales,
        "f1_cv": elegido["f1_cv_promedio"],
        "accuracy": elegido["accuracy_test"],
        "precision": elegido["precision_test"],
        "recall": elegido["recall_test"],
        "f1": elegido["f1_test"],
        "roc_auc": elegido["roc_auc_test"],
        "promovido": promovido
    })

    ARCHIVO_HISTORIAL.write_text(
        json.dumps(
            historial,
            indent=4,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


if not promovido:

    guardar_historial()

    print("\n========================================")
    print("MODELO NO PROMOVIDO")
    print("========================================")
    print(
        f"{version_modelo} ({mejor_nombre}) F1 CV "
        f"{mejor_f1_cv:.4f} < vigente "
        f"{metricas_actuales['version_modelo']} "
        f"{f1_cv_vigente:.4f}"
    )
    print("Se mantiene el modelo vigente.")

    sys.exit(3)


# Archivar el modelo vigente antes de reemplazarlo.
if ARCHIVO_MODELO.exists() and metricas_actuales:

    shutil.copy2(
        ARCHIVO_MODELO,
        CARPETA_MODELOS
        / f"modelo_{metricas_actuales['version_modelo']}.joblib"
    )


ruta_modelo = ARCHIVO_MODELO

# Escribir en temporal y reemplazar de una vez, para que
# Flask nunca lea un archivo a medio escribir.
ruta_temporal = ruta_modelo.with_suffix(".tmp")

joblib.dump(
    paquete_modelo,
    ruta_temporal,
    compress=3
)

ruta_temporal.replace(ruta_modelo)


# =========================================================
# GUARDAR MATRIZ DE CONFUSIÓN
# =========================================================

disp = ConfusionMatrixDisplay(
    confusion_matrix=matriz_final,
    display_labels=[
        "A TIEMPO",
        "RETRASADO"
    ]
)

disp.plot(
    values_format="d"
)

plt.title(
    f"Matriz de confusion - {mejor_nombre}"
)

plt.tight_layout()

ruta_matriz = (
    CARPETA_METRICAS
    / "matriz_confusion.png"
)

plt.savefig(
    ruta_matriz,
    dpi=180,
    bbox_inches="tight"
)

plt.close()


# =========================================================
# GUARDAR MÉTRICAS JSON
# =========================================================

salida_metricas = {

    "dataset": {

        "registros_totales": int(
            len(df)
        ),

        "registros_entrenamiento": int(
            len(X_train)
        ),

        "registros_prueba": int(
            len(X_test)
        ),
        "registros_externos": registros_externos,
        "registros_reales": registros_reales,

        "a_tiempo": int(
            (y == 0).sum()
        ),

        "retrasados": int(
            (y == 1).sum()
        )
    },

    "variables": COLUMNAS_MODELO,

    "modelo_seleccionado": (
        mejor_nombre
    ),

    "version_modelo": (
        version_modelo
    ),

    "criterio_seleccion": (
        "Mayor F1 promedio "
        "en validacion cruzada"
    ),

    "resultados": resultados,
    "fuente_dataset": leer_json(ARCHIVO_INFO_DATASET, None),

    "fecha_entrenamiento_utc": (
        fecha_entrenamiento
    )
}


ruta_metricas = (
    CARPETA_METRICAS
    / "metricas.json"
)

with open(
    ruta_metricas,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        salida_metricas,
        archivo,
        indent=4,
        ensure_ascii=False
    )


# =========================================================
# GUARDAR COMPARACIÓN CSV
# =========================================================

comparacion = []

for nombre, datos in resultados.items():

    comparacion.append({

        "modelo": nombre,

        "f1_cv": datos[
            "f1_cv_promedio"
        ],

        "accuracy": datos[
            "accuracy_test"
        ],

        "precision": datos[
            "precision_test"
        ],

        "recall": datos[
            "recall_test"
        ],

        "f1_test": datos[
            "f1_test"
        ],

        "roc_auc": datos[
            "roc_auc_test"
        ]
    })


df_comparacion = pd.DataFrame(
    comparacion
)

ruta_comparacion = (
    CARPETA_METRICAS
    / "comparacion_modelos.csv"
)

df_comparacion.to_csv(
    ruta_comparacion,
    index=False,
    encoding="utf-8-sig"
)


# =========================================================
# RESULTADO
# =========================================================

print("\n========================================")
print("MODELO SELECCIONADO")
print("========================================")

print(
    "Modelo:",
    mejor_nombre
)

print(
    "F1 CV:",
    round(
        mejor_f1_cv,
        4
    )
)

print(
    "Version:",
    version_modelo
)

print(
    "\nModelo guardado en:"
)

print(
    ruta_modelo
)

print(
    "\nMatriz de confusion:"
)

print(
    ruta_matriz
)

print(
    "\nMetricas:"
)

print(
    ruta_metricas
)

guardar_historial()


print("\n========================================")
print("ENTRENAMIENTO COMPLETADO")
print("========================================")
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

from sklearn.base import clone
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

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
    cross_val_score,
    RandomizedSearchCV
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

# Modelo Automatico: combinaciones de hiperparametros que prueba la
# busqueda aleatoria (cada una con validacion cruzada de 3 pliegues).
AUTOML_ITERACIONES = int(os.getenv("ML_AUTOML_ITER", "8"))

# Reentrenamiento manual (boton del dashboard): entrena aunque no haya
# pedidos reales nuevos. Lo activa ml/job_entrenamiento.py.
FORZAR = os.getenv("FORZAR_ENTRENAMIENTO") == "1"

ARCHIVO_COMPARACION_JSON = CARPETA_METRICAS / "comparacion_modelos.json"


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

    if registros_reales <= reales_ultimo and not FORZAR:

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

# 5 modelos: 4 MANUALES (hiperparametros elegidos por nosotros) y
# 1 AUTOMATICO (el sistema busca solo sus hiperparametros).
# Todos con class_weight="balanced": hay menos pedidos retrasados que
# a tiempo y, sin balancear, el modelo tenderia a decir "a tiempo".

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

    "Arbol de Decision": DecisionTreeClassifier(
        max_depth=8,
        min_samples_leaf=50,
        class_weight="balanced",
        random_state=RANDOM_STATE
    ),

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


# ---------------------------------------------------------
# MODELO AUTOMATICO
# Busqueda aleatoria de hiperparametros sobre el conjunto de
# entrenamiento (el de prueba no se toca). El mejor se compara
# despues con los otros 4 con la MISMA validacion cruzada.
# ---------------------------------------------------------

ESPACIO_AUTOML = {
    "learning_rate": [0.03, 0.05, 0.08, 0.1, 0.15],
    "max_iter": [150, 250, 400],
    "max_leaf_nodes": [15, 31, 63],
    "min_samples_leaf": [20, 50, 100, 200],
    "l2_regularization": [0.0, 0.1, 1.0],
}

print("\n========================================")
print("MODELO AUTOMATICO: BUSQUEDA DE HIPERPARAMETROS")
print("========================================")

busqueda = RandomizedSearchCV(
    HistGradientBoostingClassifier(
        class_weight="balanced",
        random_state=RANDOM_STATE
    ),
    param_distributions=ESPACIO_AUTOML,
    n_iter=AUTOML_ITERACIONES,
    scoring="f1",
    cv=StratifiedKFold(
        n_splits=3,
        shuffle=True,
        random_state=RANDOM_STATE
    ),
    random_state=RANDOM_STATE,
    n_jobs=N_JOBS
)

busqueda.fit(X_train, y_train)

print("Combinaciones probadas:", AUTOML_ITERACIONES)
print("Mejores hiperparametros:", busqueda.best_params_)
print(f"F1 de la busqueda (CV 3): {busqueda.best_score_:.4f}")

modelos["Gradient Boosting Automatico"] = clone(busqueda.best_estimator_)

automl = {
    "metodo": "RandomizedSearchCV (búsqueda aleatoria de hiperparámetros)",
    "combinaciones_probadas": AUTOML_ITERACIONES,
    "espacio_busqueda": ESPACIO_AUTOML,
    "mejores_hiperparametros": {
        clave: (valor.item() if hasattr(valor, "item") else valor)
        for clave, valor in busqueda.best_params_.items()
    },
    "f1_busqueda_cv3": float(busqueda.best_score_),
}


# ---------------------------------------------------------
# POR QUE CADA MODELO
# ---------------------------------------------------------

DESCRIPCION_MODELOS = {
    "Regresion Logistica": {
        "tipo": "Manual",
        "hiperparametros": "max_iter=2000, class_weight=balanced, datos escalados",
        "justificacion": (
            "Modelo base (línea de referencia): simple, rápido e "
            "interpretable; cada variable tiene un peso. Si un modelo "
            "complejo no lo supera, no vale la pena usarlo."
        ),
    },
    "Arbol de Decision": {
        "tipo": "Manual",
        "hiperparametros": "max_depth=8, min_samples_leaf=50, class_weight=balanced",
        "justificacion": (
            "Se explica con reglas 'si... entonces' (ej. si la carga por "
            "repartidor es alta y es hora pico -> retraso) y capta "
            "relaciones no lineales. Se limita la profundidad para que "
            "no memorice los datos."
        ),
    },
    "Random Forest": {
        "tipo": "Manual",
        "hiperparametros": "n_estimators=150, max_depth=10, min_samples_leaf=20, class_weight=balanced",
        "justificacion": (
            "Promedia 150 árboles entrenados con muestras distintas: es "
            "robusto al ruido que DoorDash agregó a sus datos y reduce "
            "el sobreajuste de un solo árbol."
        ),
    },
    "Gradient Boosting": {
        "tipo": "Manual",
        "hiperparametros": "max_iter=200, learning_rate=0.1, class_weight=balanced",
        "justificacion": (
            "Árboles en secuencia donde cada uno corrige los errores del "
            "anterior; suele ser el más preciso en datos tabulares. Se usa "
            "la versión por histogramas, rápida con ~176 mil registros."
        ),
    },
    "Gradient Boosting Automatico": {
        "tipo": "Automatico",
        "hiperparametros": ", ".join(
            f"{clave}={valor}"
            for clave, valor in automl["mejores_hiperparametros"].items()
        ),
        "justificacion": (
            "El mismo algoritmo, pero el sistema elige solo sus "
            f"hiperparámetros: prueba {AUTOML_ITERACIONES} combinaciones "
            "con validación cruzada y se queda con la de mayor F1. Sirve "
            "para comprobar si la configuración manual era la mejor."
        ),
    },
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
        ),

        **DESCRIPCION_MODELOS[nombre]
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

fecha_entrenamiento = (
    datetime.now(
        timezone.utc
    ).isoformat()
)


# =========================================================
# GUARDAR MODELO
# =========================================================


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


# ---------------------------------------------------------
# COMPARACION DE LOS 5 MODELOS (se guarda siempre, se promueva
# o no el ganador: el dashboard muestra la ultima comparacion)
# ---------------------------------------------------------

orden = sorted(
    resultados,
    key=lambda nombre: resultados[nombre]["f1_cv_promedio"],
    reverse=True
)

ARCHIVO_COMPARACION_JSON.write_text(
    json.dumps(
        {
            "fecha_entrenamiento_utc": fecha_entrenamiento,
            "version_entrenada": version_modelo,
            "promovido": promovido,
            "version_vigente": (
                version_modelo
                if promovido or not metricas_actuales
                else metricas_actuales["version_modelo"]
            ),
            "modelo_ganador": mejor_nombre,
            "criterio_seleccion": (
                "Mayor F1 promedio en validación cruzada de 5 pliegues "
                "sobre el 80 % de entrenamiento. F1 equilibra precisión y "
                "recall: importa avisar los retrasos reales sin llenar de "
                "falsas alarmas. El 20 % de prueba solo confirma."
            ),
            "dataset": {
                "registros_totales": int(len(df)),
                "registros_externos": registros_externos,
                "registros_reales": registros_reales,
                "entrenamiento": int(len(X_train)),
                "prueba": int(len(X_test)),
            },
            "automl": automl,
            "modelos": [
                {
                    "modelo": nombre,
                    "posicion": posicion,
                    "ganador": nombre == mejor_nombre,
                    **{
                        clave: valor
                        for clave, valor in resultados[nombre].items()
                    },
                }
                for posicion, nombre in enumerate(orden, start=1)
            ],
        },
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
    "automl": automl,
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
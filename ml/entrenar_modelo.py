import json
from pathlib import Path
from datetime import datetime, timezone

import joblib
import matplotlib.pyplot as plt
import pandas as pd

from sklearn.ensemble import (
    RandomForestClassifier,
    GradientBoostingClassifier
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

COLUMNAS_MODELO = [
    "distancia_km",
    "duracion_estimada_min",
    "tiempo_preparacion_estimado_min",
    "cantidad_items",
    "hora_pedido",
    "dia_semana",
    "hora_pico",
    "fin_semana",
    "pedidos_activos"
]

TARGET = "retraso"


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
        n_estimators=350,
        max_depth=8,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1
    ),

    "Gradient Boosting": GradientBoostingClassifier(
        n_estimators=150,
        learning_rate=0.05,
        max_depth=3,
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
        n_jobs=-1
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
# GUARDAR MODELO
# =========================================================

version_modelo = "v1.0"

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


ruta_modelo = (
    CARPETA_MODELOS
    / "modelo_final.joblib"
)

joblib.dump(
    paquete_modelo,
    ruta_modelo
)


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

print("\n========================================")
print("ENTRENAMIENTO COMPLETADO")
print("========================================")
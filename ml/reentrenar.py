"""
Reentrenamiento del modelo con los datos actuales del sistema:

    PostgreSQL (sinteticos + reales entregados)
        -> exportar_dataset.py -> pedidos_ml.csv
        -> entrenar_modelo.py  -> nueva version

Codigos de salida:
    0 = nueva version entrenada y promovida
    2 = no hay pedidos reales nuevos, no se reentrena
    3 = nueva version entrenada pero no mejora; se mantiene la vigente
    otro = error

Uso (desde la raiz del proyecto):
    python ml/reentrenar.py
"""

import subprocess
import sys
from pathlib import Path


CARPETA_ML = Path(__file__).resolve().parent


for script in ("exportar_dataset.py", "entrenar_modelo.py"):

    print(f"\n>>> {script}")

    resultado = subprocess.run(
        [sys.executable, str(CARPETA_ML / script)],
        cwd=CARPETA_ML.parent
    )

    if resultado.returncode != 0:
        sys.exit(resultado.returncode)

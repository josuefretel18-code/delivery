let usuarioAdmin = null;
let catalogoAdmin = [];


/* ========================================================
   INICIO
======================================================== */

document.addEventListener(
    "DOMContentLoaded",
    () => {

        configurarLoginAdmin();
        verificarAdminGuardado();

        document.getElementById(
            "btnActualizarPedidos"
        ).addEventListener(
            "click",
            () => cargarPedidosAdmin()
        );

        document.getElementById(
            "btnCerrarSesionAdmin"
        ).addEventListener(
            "click",
            cerrarSesionAdmin
        );
        document.getElementById(
            "btnGestionProductos"
        ).addEventListener(
            "click",
            cargarProductosAdmin
        );
        document.getElementById(
            "btnDashboardML"
        ).addEventListener(
            "click",
            cargarDashboardML
        );
        document.getElementById(
            "btnNuevoProducto"
        ).addEventListener(
            "click",
            abrirNuevoProducto
        );


        document.getElementById(
            "btnCancelarProducto"
        ).addEventListener(
            "click",
            cerrarFormularioProducto
        );


        document.getElementById(
            "btnGuardarProducto"
        ).addEventListener(
            "click",
            guardarProductoAdmin
        );


        document.getElementById(
            "btnNuevaCategoria"
        ).addEventListener(
            "click",
            mostrarNuevaCategoria
        );


        document.getElementById(
            "btnCancelarCategoria"
        ).addEventListener(
            "click",
            ocultarNuevaCategoria
        );


        document.getElementById(
            "btnGuardarCategoria"
        ).addEventListener(
            "click",
            guardarCategoriaAdmin
        );

    }
);


/* ========================================================
   LOGIN
======================================================== */

function configurarLoginAdmin() {

    document.getElementById(
        "formAdminLogin"
    ).addEventListener(
        "submit",
        loginAdmin
    );

}


async function loginAdmin(
    event
) {

    event.preventDefault();


    const correo =
        document.getElementById(
            "adminCorreo"
        ).value.trim();


    const password =
        document.getElementById(
            "adminPassword"
        ).value;


    const mensaje =
        document.getElementById(
            "mensajeAdminLogin"
        );


    mensaje.classList.add(
        "d-none"
    );


    try {

        const respuesta =
            await fetch(
                "/api/auth/login",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        correo,
                        password
                    })
                }
            );


        const datos =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            throw new Error(
                datos.mensaje ||
                "Datos incorrectos."
            );

        }


        localStorage.setItem(
            "kimbos_admin_token",
            datos.token
        );


        const correcto =
            await cargarPerfilAdmin();


        if (!correcto) {

            localStorage.removeItem(
                "kimbos_admin_token"
            );

            throw new Error(
                "Esta cuenta no tiene permisos de administrador u operador."
            );

        }


        mostrarPanelAdmin();

        await cargarPedidosAdmin();


    } catch (error) {

        mensaje.textContent =
            error.message;

        mensaje.classList.remove(
            "d-none"
        );

    }

}


/* ========================================================
   PERFIL
======================================================== */

async function cargarPerfilAdmin() {

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    if (!token) {
        return false;
    }


    try {

        const respuesta =
            await fetch(
                "/api/auth/me",
                {
                    headers: {
                        "Authorization":
                            `Bearer ${token}`
                    }
                }
            );


        if (!respuesta.ok) {
            return false;
        }


        const datos =
            await respuesta.json();


        usuarioAdmin =
            datos.usuario || datos;


        if (
            usuarioAdmin.rol !== "ADMIN" &&
            usuarioAdmin.rol !== "OPERADOR"
        ) {

            usuarioAdmin = null;

            return false;

        }


        return true;


    } catch {

        return false;

    }

}


async function verificarAdminGuardado() {

    const correcto =
        await cargarPerfilAdmin();


    if (correcto) {

        mostrarPanelAdmin();

        await cargarPedidosAdmin();

    }

}


/* ========================================================
   PANEL
======================================================== */

function mostrarPanelAdmin() {

    document.getElementById(
        "vistaLogin"
    ).classList.add(
        "d-none"
    );


    document.getElementById(
        "vistaPanel"
    ).classList.remove(
        "d-none"
    );


    const nombre =
        usuarioAdmin.nombre ||
        usuarioAdmin.nombre_completo ||
        "Administrador";


    document.getElementById(
        "nombreAdmin"
    ).textContent =
        nombre;

}


/* ========================================================
   PEDIDOS
======================================================== */

async function cargarPedidosAdmin(silencioso = false) {

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    const cargando =
        document.getElementById(
            "cargandoAdmin"
        );


    const lista =
        document.getElementById(
            "listaPedidosAdmin"
        );


    const sinPedidos =
        document.getElementById(
            "sinPedidosAdmin"
        );


    // En la actualizacion automatica no se vacia la lista (sin parpadeo)
    if (!silencioso) {

        cargando.classList.remove(
            "d-none"
        );


        lista.innerHTML = "";


        sinPedidos.classList.add(
            "d-none"
        );
    }


    // Repartidores (para el selector de asignacion) y pedidos se
    // piden al mismo tiempo, no uno despues del otro.
    const repartidoresListos =
        cargarRepartidoresAdmin();


    try {

        const respuesta =
            await fetch(
                "/api/pedidos",
                {
                    headers: {
                        "Authorization":
                            `Bearer ${token}`
                    }
                }
            );


        const datos =
            await respuesta.json();


        await repartidoresListos;


        cargando.classList.add(
            "d-none"
        );


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            throw new Error(
                datos.mensaje ||
                "No se pudieron cargar los pedidos."
            );

        }


        if (
            !datos.pedidos ||
            datos.pedidos.length === 0
        ) {

            sinPedidos.classList.remove(
                "d-none"
            );

            actualizarContadores(
                []
            );

            return;

        }


        actualizarContadores(
            datos.pedidos
        );


        renderizarPedidosAdmin(
            datos.pedidos
        );


    } catch (error) {

        cargando.classList.add(
            "d-none"
        );

        alert(
            error.message
        );

    }

}


/* ========================================================
   DASHBOARD ML
======================================================== */

let temporizadorDashboardML = null;


async function cargarDashboardML(opciones) {

    // Silencioso = refresco automático: sin vaciar ni mostrar "Cargando".
    // (Desde el botón llega el evento click, que no trae "silencioso").
    const silencioso =
        opciones?.silencioso === true;

    clearTimeout(temporizadorDashboardML);

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );

    const cargando =
        document.getElementById(
            "cargandoDashboardML"
        );

    const contenido =
        document.getElementById(
            "contenidoDashboardML"
        );

    if (!silencioso) {
        cargando.classList.remove("d-none");
        contenido.innerHTML = "";
    }

    try {

        const respuesta =
            await fetch(
                "/api/pedidos/ml/resumen",
                {
                    headers: {
                        "Authorization":
                            `Bearer ${token}`
                    }
                }
            );

        const datos =
            await respuesta.json();

        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            throw new Error(
                datos.mensaje ||
                "No se pudo cargar el dashboard ML."
            );

        }

        renderizarDashboardML(datos);

    } catch (error) {

        contenido.innerHTML = `
            <div class="alert alert-danger">
                ${escaparHtmlAdmin(error.message)}
            </div>
        `;

    } finally {

        cargando.classList.add("d-none");

    }

}


function porcentajeML(valor) {

    return valor === null || valor === undefined
        ? "--"
        : `${(valor * 100).toFixed(1)}%`;

}


function tarjetaMetricaML(titulo, valor, ayuda) {

    return `
        <div class="col-6 col-lg">
            <div class="metrica-ml-card">
                <small>${titulo}</small>
                <strong>${valor}</strong>
                <span>${ayuda}</span>
            </div>
        </div>
    `;

}


function matrizConfusionML(matriz) {

    const [[vn, fp], [fn, vp]] = matriz;

    return `
        <div class="matriz-ml">

            <div></div>
            <div class="matriz-ml-eje">Predijo A tiempo</div>
            <div class="matriz-ml-eje">Predijo Retrasado</div>

            <div class="matriz-ml-eje">Real A tiempo</div>
            <div class="matriz-ml-celda acierto">
                <strong>${vn}</strong>
                <span>Acierto</span>
            </div>
            <div class="matriz-ml-celda error">
                <strong>${fp}</strong>
                <span>Falsa alarma</span>
            </div>

            <div class="matriz-ml-eje">Real Retrasado</div>
            <div class="matriz-ml-celda error">
                <strong>${fn}</strong>
                <span>Retraso no detectado</span>
            </div>
            <div class="matriz-ml-celda acierto">
                <strong>${vp}</strong>
                <span>Retraso detectado</span>
            </div>

        </div>
    `;

}


function renderizarDashboardML(datos) {

    const modelo = datos.modelo;
    const reales = datos.reales;

    let html = "";


    // ---------- Evaluación del modelo ----------

    if (modelo) {

        const comparacion =
            modelo.comparacion
                .map(fila => `
                    <tr class="${fila.modelo === modelo.nombre ? "fila-ml-seleccionada" : ""}">
                        <td>
                            ${escaparHtmlAdmin(fila.modelo)}
                            ${fila.modelo === modelo.nombre ? " ✓" : ""}
                        </td>
                        <td>${fila.f1_cv.toFixed(3)}</td>
                        <td>${porcentajeML(fila.accuracy)}</td>
                        <td>${porcentajeML(fila.precision)}</td>
                        <td>${porcentajeML(fila.recall)}</td>
                        <td>${fila.f1.toFixed(3)}</td>
                        <td>${fila.roc_auc.toFixed(3)}</td>
                    </tr>
                `)
                .join("");

        html += `
            <section class="seccion-ml">

                <h5 class="fw-bold mb-1">
                    1. Evaluación del modelo
                </h5>

                <p class="text-secondary small mb-2">
                    ${escaparHtmlAdmin(modelo.nombre)}
                    ${escaparHtmlAdmin(modelo.version || "")}
                    · Prueba con ${modelo.dataset.registros_prueba.toLocaleString("es-PE")}
                    de ${modelo.dataset.registros_totales.toLocaleString("es-PE")} registros reales
                    (${(modelo.dataset.registros_externos ?? 0).toLocaleString("es-PE")} DoorDash
                    + ${modelo.dataset.registros_reales ?? 0} Kimbos)
                    · ${escaparHtmlAdmin(modelo.criterio || "")}
                </p>

                ${
                    modelo.fuente_dataset
                        ? `
                            <div class="alert alert-light border small mb-3">
                                <strong>Fuente:</strong>
                                ${escaparHtmlAdmin(modelo.fuente_dataset.fuente_externa)}.
                                ${escaparHtmlAdmin(modelo.fuente_dataset.descripcion_externa)}
                                <br>
                                <strong>Regla de retraso:</strong>
                                ${escaparHtmlAdmin(modelo.fuente_dataset.regla_retraso)}
                            </div>
                        `
                        : ""
                }

                <div class="row g-3 mb-4">
                    ${tarjetaMetricaML("Accuracy", porcentajeML(modelo.accuracy), "Predicciones correctas del total")}
                    ${tarjetaMetricaML("Precision", porcentajeML(modelo.precision), "Cuando avisa retraso, acierta")}
                    ${tarjetaMetricaML("Recall", porcentajeML(modelo.recall), "Retrasos reales que detecta")}
                    ${tarjetaMetricaML("F1-score", modelo.f1.toFixed(3), "Balance precision / recall")}
                    ${tarjetaMetricaML("ROC-AUC", modelo.roc_auc.toFixed(3), "Capacidad de separar clases")}
                </div>

                <div class="row g-4 align-items-start">

                    <div class="col-lg-5">
                        <h6 class="fw-bold">Matriz de confusión</h6>
                        ${matrizConfusionML(modelo.matriz_confusion)}
                    </div>

                    <div class="col-lg-7">
                        <h6 class="fw-bold">Comparación de modelos</h6>
                        <div class="table-responsive">
                            <table class="table table-sm tabla-ml">
                                <thead>
                                    <tr>
                                        <th>Modelo</th>
                                        <th>F1 CV</th>
                                        <th>Accuracy</th>
                                        <th>Precision</th>
                                        <th>Recall</th>
                                        <th>F1</th>
                                        <th>ROC-AUC</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${comparacion}
                                </tbody>
                            </table>
                        </div>
                    </div>

                </div>

            </section>
        `;

    } else {

        // Sin metricas: la API de ML no respondio o aun no hay modelo.
        const errorApi =
            datos.reentrenamiento?.resultado === "ERROR"
                ? datos.reentrenamiento.mensaje
                : null;

        html += `
            <div class="alert alert-warning">
                ${errorApi
                    ? escaparHtmlAdmin(errorApi) +
                      ". Revisa ML_API_URL y ML_API_KEY."
                    : "No se encontró ml/metrics/metricas.json. Ejecuta el entrenamiento del modelo."}
            </div>
        `;

    }


    // ---------- Pedidos reales ----------

    html += `
        <section class="seccion-ml">

            <h5 class="fw-bold mb-1">
                2. Predicciones en pedidos reales
            </h5>

            <p class="text-secondary small mb-3">
                Qué predijo el modelo en cada pedido de Kimbos y qué pasó realmente al entregarlo.
            </p>

            <div class="row g-3 mb-3">
                ${tarjetaMetricaML("Pedidos evaluados", reales.evaluados, `${reales.pendientes} pendiente(s) de entrega`)}
                ${tarjetaMetricaML("Aciertos", reales.correctas, "La predicción coincidió")}
                ${tarjetaMetricaML("Fallos", reales.incorrectas, "La predicción no coincidió")}
                ${tarjetaMetricaML("% de acierto", porcentajeML(reales.accuracy), "Aciertos ÷ evaluados")}
            </div>
    `;

    if (reales.detalle.length === 0) {

        html += `
            <div class="alert alert-light border">
                Aún no hay pedidos reales con predicción del modelo actual.
                (Las predicciones del modelo sintético v1.0, ya descartado, no se cuentan.)
            </div>
        `;

    } else {

        const filasDetalle =
            reales.detalle
                .map(pedido => {

                    const textoClase = clase =>
                        clase === "RETRASADO" ? "Retrasado" : "A tiempo";

                    const resultado =
                        pedido.acerto === null
                            ? `<span class="estado-version">Pendiente</span>`
                            : pedido.acerto
                                ? `<span class="estado-version activa">✓ Acertó</span>`
                                : `<span class="estado-version rechazada">✕ Falló</span>`;

                    return `
                        <tr>
                            <td>
                                <strong>${escaparHtmlAdmin(pedido.codigo)}</strong>
                                <div class="small text-secondary">
                                    ${formatearFechaAdmin(pedido.fecha_pedido)}
                                </div>
                            </td>
                            <td>
                                ${textoClase(pedido.prediccion)}
                                <div class="small text-secondary">
                                    ${pedido.probabilidad_porcentaje ?? "--"}% riesgo
                                    · ${escaparHtmlAdmin(pedido.modelo_version || "")}
                                </div>
                            </td>
                            <td>
                                ${
                                    pedido.resultado_real
                                        ? `
                                            ${textoClase(pedido.resultado_real)}
                                            <div class="small text-secondary">
                                                ${pedido.duracion_real_min} min
                                                (estimado ${pedido.tiempo_estimado_min ?? "--"} min)
                                            </div>
                                        `
                                        : `<span class="text-secondary">En curso</span>`
                                }
                            </td>
                            <td>${resultado}</td>
                        </tr>
                    `;

                })
                .join("");

        html += `
            <div class="table-responsive">
                <table class="table table-sm tabla-ml align-middle">
                    <thead>
                        <tr>
                            <th>Pedido</th>
                            <th>Predicción del modelo</th>
                            <th>Resultado real</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${filasDetalle}
                    </tbody>
                </table>
            </div>
        `;

        // Matriz y métricas avanzadas solo con datos suficientes.
        if (reales.evaluados >= 30) {

            html += `
                <div class="row g-4 align-items-start mt-1">

                    <div class="col-lg-5">
                        <h6 class="fw-bold">Matriz de confusión</h6>
                        ${matrizConfusionML(reales.matriz_confusion)}
                    </div>

                    <div class="col-lg-7">
                        <div class="row g-3">
                            ${tarjetaMetricaML("Precision", porcentajeML(reales.precision), "Cuando avisa retraso, acierta")}
                            ${tarjetaMetricaML("Recall", porcentajeML(reales.recall), "Retrasos reales que detecta")}
                            ${tarjetaMetricaML("F1-score", reales.f1 === null ? "--" : reales.f1.toFixed(3), "Balance precision / recall")}
                        </div>
                    </div>

                </div>
            `;

        } else {

            html += `
                <p class="small text-secondary mb-0">
                    La matriz de confusión y las métricas Precision, Recall y F1 de pedidos reales
                    se mostrarán al llegar a 30 pedidos evaluados (van ${reales.evaluados}).
                </p>
            `;

        }

    }

    html += `</section>`;


    // ---------- Evolución del modelo ----------

    if (modelo) {

        const realesEnModelo =
            modelo.dataset.registros_reales ?? 0;

        // Nuevos respecto del último entrenamiento,
        // aunque esa versión no haya sido promovida.
        const realesUltimoEntrenamiento = Math.max(
            realesEnModelo,
            ...datos.historial.map(
                version => version.registros_reales
            )
        );

        const realesNuevos = Math.max(
            reales.entregados_con_resultado - realesUltimoEntrenamiento,
            0
        );

        // Antes del primer reentrenamiento no hay historial:
        // se muestra la versión vigente.
        const historial =
            datos.historial.length > 0
                ? datos.historial
                : [{
                    version: modelo.version,
                    fecha_entrenamiento_utc: modelo.fecha_entrenamiento,
                    modelo: modelo.nombre,
                    registros_externos: modelo.dataset.registros_externos ?? 0,
                    registros_reales: 0,
                    f1_cv: modelo.comparacion.find(
                        fila => fila.modelo === modelo.nombre
                    ).f1_cv,
                    accuracy: modelo.accuracy,
                    f1: modelo.f1,
                    roc_auc: modelo.roc_auc,
                    promovido: true
                }];

        const filasHistorial =
            historial
                .slice(-10)
                .reverse()
                .map(version => {

                    const estado =
                        version.version === modelo.version
                            ? `<span class="estado-version activa">Activa</span>`
                            : version.promovido
                                ? `<span class="estado-version">Anterior</span>`
                                : `<span class="estado-version rechazada">No mejoró</span>`;

                    return `
                        <tr class="${version.version === modelo.version ? "fila-ml-seleccionada" : ""}">
                            <td>${escaparHtmlAdmin(version.version)}</td>
                            <td>${formatearFechaAdmin(version.fecha_entrenamiento_utc)}</td>
                            <td>${escaparHtmlAdmin(version.modelo)}</td>
                            <td>${(version.registros_externos ?? 0).toLocaleString("es-PE")}</td>
                            <td>${version.registros_reales}</td>
                            <td>${version.f1_cv.toFixed(3)}</td>
                            <td>${porcentajeML(version.accuracy)}</td>
                            <td>${version.f1.toFixed(3)}</td>
                            <td>${version.roc_auc.toFixed(3)}</td>
                            <td>${estado}</td>
                        </tr>
                    `;

                })
                .join("");

        // En producción no está el dataset DoorDash: no se reentrena.
        const reentrenoDisponible =
            datos.reentrenamiento?.disponible !== false;

        const puedeReentrenar =
            reentrenoDisponible &&
            usuarioAdmin &&
            usuarioAdmin.rol === "ADMIN";

        const estadoReentreno =
            datos.reentrenamiento || {};

        const avisoReentreno =
            estadoReentreno.en_curso
                ? `
                    <div class="alert alert-info small d-flex align-items-center gap-2">
                        <span class="spinner-border spinner-border-sm"></span>
                        Reentrenando el modelo con los pedidos entregados
                        ${estadoReentreno.donde ? `en ${escaparHtmlAdmin(estadoReentreno.donde)}` : ""}...
                        (tarda unos minutos; esta sección se actualiza sola)
                    </div>
                `
                : estadoReentreno.fin
                    ? `
                        <div class="alert ${estadoReentreno.resultado === "ERROR" ? "alert-danger" : "alert-light border"} small">
                            <strong>Último reentrenamiento
                            (${estadoReentreno.origen === "AUTOMATICO" ? "automático" : "manual"},
                            ${formatearFechaAdmin(estadoReentreno.fin)}):</strong>
                            ${escaparHtmlAdmin(estadoReentreno.mensaje || "")}
                        </div>
                    `
                    : "";

        html += `
            <section class="seccion-ml">

                <div class="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-3">

                    <div>
                        <h5 class="fw-bold mb-1">
                            3. Evolución del modelo
                        </h5>

                        <p class="text-secondary small mb-0">
                            Versión activa ${escaparHtmlAdmin(modelo.version)}:
                            entrenada con ${(modelo.dataset.registros_totales - realesEnModelo).toLocaleString("es-PE")} pedidos DoorDash
                            + ${realesEnModelo} pedidos reales de Kimbos
                            · <strong>${realesNuevos}</strong> pedido(s) real(es) entregado(s)
                            nuevo(s) desde el último entrenamiento
                        </p>
                    </div>

                    ${
                        // Solo si hay pedidos entregados sin usar (el
                        // automático falló o está apagado): es un respaldo.
                        puedeReentrenar && realesNuevos > 0 && !estadoReentreno.en_curso
                            ? `
                                <button
                                    id="btnReentrenarML"
                                    class="btn btn-dark"
                                    type="button"
                                    onclick="reentrenarModeloML()"
                                >
                                    ${textoBotonReentrenar(estadoReentreno.automatico)}
                                </button>
                            `
                            : ""
                    }

                </div>

                ${
                    puedeReentrenar && realesNuevos > 0 && !estadoReentreno.en_curso
                        ? `
                            <div class="alert alert-warning small">
                                Hay <strong>${realesNuevos}</strong> pedido(s) entregado(s) que aún no
                                se usaron para entrenar.
                                ${
                                    estadoReentreno.automatico
                                        ? "El reentrenamiento automático no llegó a procesarlos: puedes reintentarlo."
                                        : "El reentrenamiento automático está apagado: puedes entrenar manualmente."
                                }
                            </div>
                        `
                        : ""
                }

                ${
                    reentrenoDisponible
                        ? ""
                        : `
                            <div class="alert alert-light border small">
                                <strong>Servidor de producción:</strong> aquí el modelo solo predice.
                                El reentrenamiento se ejecuta en el equipo de desarrollo (con los pedidos
                                reales de esta misma base de datos) y la nueva versión se publica con
                                <code>git push</code>.
                            </div>
                        `
                }

                <p class="small text-secondary">
                    ${
                        estadoReentreno.automatico
                            ? "<strong>Reentrenamiento automático activo:</strong> cada vez que un pedido se marca como entregado, "
                            : "Reentrenamiento manual: "
                    }
                    se une el dataset DoorDash con los pedidos reales de Kimbos entregados
                    y se entrena una nueva versión. Solo reemplaza al modelo activo
                    si su F1 en validación cruzada es igual o mejor.
                    ${
                        estadoReentreno.donde
                            ? `<br><strong>Entrenamiento en:</strong> ${escaparHtmlAdmin(estadoReentreno.donde)}`
                            : ""
                    }
                </p>

                ${avisoReentreno}


                <div class="table-responsive">
                    <table class="table table-sm tabla-ml">
                        <thead>
                            <tr>
                                <th>Versión</th>
                                <th>Fecha</th>
                                <th>Modelo</th>
                                <th>DoorDash</th>
                                <th>Kimbos</th>
                                <th>F1 CV</th>
                                <th>Accuracy</th>
                                <th>F1</th>
                                <th>ROC-AUC</th>
                                <th>Estado</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${filasHistorial}
                        </tbody>
                    </table>
                </div>

            </section>
        `;

    }


    document.getElementById(
        "contenidoDashboardML"
    ).innerHTML = html;


    // Mientras se reentrena, refrescar cada 10 s (solo si el
    // modal sigue abierto).
    if (datos.reentrenamiento?.en_curso) {

        temporizadorDashboardML = setTimeout(() => {

            const modalAbierto =
                document.getElementById(
                    "modalDashboardML"
                ).classList.contains("show");

            if (modalAbierto) {
                cargarDashboardML({ silencioso: true });
            }

        }, 10000);

    }

}


function textoBotonReentrenar(automatico) {

    return automatico
        ? "↻ Reintentar reentrenamiento"
        : "↻ Reentrenar con datos actuales";

}


async function reentrenarModeloML() {

    if (
        !confirm(
            "¿Reentrenar el modelo con el dataset DoorDash y los pedidos reales entregados de Kimbos?"
        )
    ) {
        return;
    }

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );

    const boton =
        document.getElementById(
            "btnReentrenarML"
        );

    const textoOriginal = boton.textContent;

    boton.disabled = true;
    boton.textContent = "Reentrenando...";

    try {

        const respuesta =
            await fetch(
                "/api/pedidos/ml/reentrenar",
                {
                    method: "POST",
                    headers: {
                        "Authorization":
                            `Bearer ${token}`
                    }
                }
            );

        const datos =
            await respuesta.json();

        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            throw new Error(
                datos.mensaje ||
                "No se pudo reentrenar el modelo."
            );

        }

        // El resultado se muestra en "Último reentrenamiento".
        await cargarDashboardML();

    } catch (error) {

        boton.disabled = false;
        boton.textContent = textoOriginal;

        alert(error.message);

    }

}
/* ========================================================
   CONTADORES
======================================================== */

function actualizarContadores(pedidos) {

    let recibidos = 0;
    let preparando = 0;
    let camino = 0;
    let entregados = 0;


    pedidos.forEach(pedido => {

        switch (pedido.estado.codigo) {

            case "REGISTRADO":
                recibidos++;
                break;

            case "PREPARANDO":
                preparando++;
                break;

            case "EN_RUTA":
                camino++;
                break;

            case "ENTREGADO":
                entregados++;
                break;
        }

    });


    document.getElementById(
        "totalRecibidos"
    ).textContent = recibidos;


    document.getElementById(
        "totalPreparando"
    ).textContent = preparando;


    document.getElementById(
        "totalCamino"
    ).textContent = camino;


    document.getElementById(
        "totalEntregados"
    ).textContent = entregados;

}
/* ========================================================
   RENDERIZAR PEDIDOS
======================================================== */

function renderizarPedidosAdmin(pedidos) {

    const contenedor =
        document.getElementById(
            "listaPedidosAdmin"
        );


    const tarjetas = [];


    pedidos.forEach(pedido => {

        const productos =
            pedido.productos
                .map(producto => `
                    <div class="producto-admin">

                        <span>
                            ${producto.cantidad}
                            ×
                            ${escaparHtmlAdmin(
                                producto.nombre
                            )}
                        </span>

                        <strong>
                            S/
                            ${Number(
                                producto.subtotal
                            ).toFixed(2)}
                        </strong>

                    </div>
                `)
                .join("");


        const accion =
            obtenerAccionPedido(
                pedido.estado.codigo
            );


        tarjetas.push(`
            <div class="col-12 col-lg-6">

                <div class="pedido-admin-card">

                    <div
                        class="
                            d-flex
                            justify-content-between
                            align-items-start
                            gap-3
                        "
                    >

                        <div>

                            <div class="codigo-admin">
                                ${escaparHtmlAdmin(
                                    pedido.codigo
                                )}
                            </div>

                            <small class="text-secondary">
                                ${formatearFechaAdmin(
                                    pedido.fecha_pedido
                                )}
                            </small>

                        </div>

                        <span class="estado-admin">
                            ${accion.estadoVisible}
                        </span>

                    </div>


                    <div class="cliente-admin">

                        <strong>
                            ${escaparHtmlAdmin(
                                pedido.destinatario_nombre
                            )}
                        </strong>

                        <div class="small mt-1">
                            📞
                            ${escaparHtmlAdmin(
                                pedido.destinatario_telefono
                            )}
                        </div>

                        <div class="small mt-2">

                            ${
                                pedido.latitud_destino !== null &&
                                pedido.longitud_destino !== null

                                    ? `
                                        <a
                                            class="link-mapa-admin"
                                            href="https://www.google.com/maps/search/?api=1&query=${pedido.latitud_destino},${pedido.longitud_destino}"
                                            target="_blank"
                                            rel="noopener noreferrer"
                                        >
                                            📍
                                            ${escaparHtmlAdmin(
                                                pedido.direccion_destino
                                            )}
                                        </a>
                                    `

                                    : `
                                        <span class="text-secondary">
                                            📍
                                            ${escaparHtmlAdmin(
                                                pedido.direccion_destino
                                            )}
                                        </span>
                                    `
                            }

                        </div>

                    </div>


                    <div class="productos-admin">

                        ${productos}

                    </div>


                    <div
                        class="
                            d-flex
                            justify-content-between
                            mb-2
                        "
                    >

                        <span>
                            Delivery
                        </span>

                        <strong>
                            S/
                            ${Number(
                                pedido.costo_delivery
                            ).toFixed(2)}
                        </strong>

                    </div>


                    <div
                        class="
                            d-flex
                            justify-content-between
                            align-items-center
                            mb-3
                        "
                    >

                        <strong>
                            Total
                        </strong>

                        <span class="total-admin">
                            S/
                            ${Number(
                                pedido.total
                            ).toFixed(2)}
                        </span>

                    </div>


                    <div class="small text-secondary mb-3">

                        ⏱ Preparación:
                        ${pedido.tiempo_preparacion_estimado_min ?? "--"}
                        min

                        ·

                        🚗 Ruta:
                        ${pedido.duracion_estimada_min ?? "--"}
                        min

                        ${
                            pedido.espera_repartidor_min
                                ? `· 🛵 Espera repartidor: ${pedido.espera_repartidor_min} min`
                                : ""
                        }

                    </div>
                    ${
                        pedido.prediccion_ml
                            ? `
                                <div
                                    class="
                                        prediccion-ml-admin
                                        ${
                                            pedido.prediccion_ml.clase === "RETRASADO"
                                                ? "prediccion-ml-riesgo"
                                                : "prediccion-ml-tiempo"
                                        }
                                    "
                                >

                                    <div
                                        class="
                                            d-flex
                                            justify-content-between
                                            align-items-center
                                            gap-3
                                        "
                                    >

                                        <div>

                                            <div class="prediccion-ml-titulo">
                                                🤖 Predicción ML
                                            </div>

                                            <div class="prediccion-ml-clase">

                                                ${
                                                    pedido.prediccion_ml.clase === "RETRASADO"
                                                        ? "Posible retraso"
                                                        : "A tiempo"
                                                }

                                            </div>

                                        </div>


                                        <div class="prediccion-ml-porcentaje">

                                            ${
                                                Number(
                                                    pedido.prediccion_ml
                                                        .probabilidad_porcentaje
                                                ).toFixed(2)
                                            }%

                                        </div>

                                    </div>


                                    <div class="prediccion-ml-detalle">

                                        Riesgo estimado de retraso

                                        ·

                                        Modelo
                                        ${
                                            escaparHtmlAdmin(
                                                pedido.prediccion_ml.version || "--"
                                            )
                                        }

                                    </div>

                                </div>
                            `
                            : ""
                    }
                    ${htmlAlertaAgentes(pedido)}
                    ${
                        pedido.resultado_real
                            ? `
                                <div
                                    class="
                                        resultado-real-admin
                                        ${
                                            pedido.resultado_real.clase === "RETRASADO"
                                                ? "resultado-real-retrasado"
                                                : "resultado-real-tiempo"
                                        }
                                    "
                                >

                                    <div
                                        class="
                                            d-flex
                                            justify-content-between
                                            align-items-center
                                            gap-3
                                        "
                                    >

                                        <div>

                                            <div class="resultado-real-titulo">
                                                📊 Resultado real
                                            </div>

                                            <div class="resultado-real-clase">

                                                ${
                                                    pedido.resultado_real.clase === "RETRASADO"
                                                        ? "Retrasado"
                                                        : "A tiempo"
                                                }

                                            </div>

                                        </div>


                                        <div class="resultado-real-minutos">

                                            ${
                                                pedido.resultado_real
                                                    .duracion_real_min
                                            }
                                            min

                                        </div>

                                    </div>


                                    ${
                                        pedido.prediccion_ml
                                            ? `
                                                <div class="resultado-comparacion">

                                                    ${
                                                        pedido.prediccion_ml.clase ===
                                                        pedido.resultado_real.clase

                                                            ? "✓ La predicción coincidió con el resultado real"

                                                            : "✕ La predicción no coincidió con el resultado real"
                                                    }

                                                </div>
                                            `
                                            : ""
                                    }

                                </div>
                            `
                            : ""
                    }


                    ${
                        pedido.indicaciones_entrega
                            ? `
                                <div
                                    class="
                                        alert
                                        alert-light
                                        border
                                        small
                                    "
                                >
                                    <strong>
                                        Indicaciones:
                                    </strong>

                                    ${escaparHtmlAdmin(
                                        pedido.indicaciones_entrega
                                    )}
                                </div>
                            `
                            : ""
                    }


                    ${htmlRepartidorPedido(pedido)}


                    ${
                        seguimientoEntrega(pedido)
                            ? seguimientoEntrega(pedido)
                            : accion.siguienteEstado
                            ? `
                                <button
                                    class="btn-siguiente"
                                    onclick="
                                        cambiarEstadoPedido(
                                            ${pedido.id},
                                            '${accion.siguienteEstado}'
                                        )
                                    "
                                >
                                    ${accion.textoBoton}
                                </button>
                            `
                            : `
                                <button
                                    class="btn-siguiente"
                                    disabled
                                >
                                    ✓ Pedido entregado
                                </button>
                            `
                    }

                </div>

            </div>
        `);

    });


    contenedor.innerHTML = tarjetas.join("");

}
/* ========================================================
   FLUJO SIMPLIFICADO
======================================================== */

function obtenerAccionPedido(estado) {

    switch (estado) {

        case "REGISTRADO":

            return {
                estadoVisible:
                    "Pedido recibido",

                siguienteEstado:
                    "PREPARANDO",

                textoBoton:
                    "Iniciar preparación"
            };


        case "PREPARANDO":

            return {
                estadoVisible:
                    "En preparación",

                siguienteEstado:
                    "EN_RUTA",

                textoBoton:
                    "Enviar pedido"
            };


        case "EN_RUTA":

            return {
                estadoVisible:
                    "En camino",

                siguienteEstado:
                    "ENTREGADO",

                textoBoton:
                    "Marcar como entregado"
            };


        case "ENTREGADO":

            return {
                estadoVisible:
                    "Entregado",

                siguienteEstado:
                    null,

                textoBoton:
                    null
            };


        default:

            return {
                estadoVisible:
                    estado,

                siguienteEstado:
                    null,

                textoBoton:
                    null
            };
    }

}
/* ========================================================
   CAMBIAR ESTADO
======================================================== */

async function cambiarEstadoPedido(
    pedidoId,
    nuevoEstado
) {

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    if (!token) {
        return;
    }


    try {

        const respuesta =
            await fetch(
                `/api/pedidos/${pedidoId}/estado`,
                {
                    method: "PATCH",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Authorization":
                            `Bearer ${token}`
                    },

                    body:
                        JSON.stringify(
                            cuerpoCambioEstado(
                                pedidoId,
                                nuevoEstado
                            )
                        )
                }
            );


        const datos =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            alert(
                datos.mensaje ||
                "No se pudo actualizar el pedido."
            );

            return;
        }


        await cargarPedidosAdmin();


    } catch (error) {

        console.error(error);

        alert(
            "No se pudo conectar con el servidor."
        );

    }

}
/* ========================================================
   UTILIDADES
======================================================== */

function formatearFechaAdmin(fecha) {

    if (!fecha) {
        return "";
    }


    return new Date(fecha)
        .toLocaleString(
            "es-PE",
            {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit"
            }
        );

}


function escaparHtmlAdmin(texto) {

    const elemento =
        document.createElement(
            "div"
        );


    elemento.textContent =
        texto ?? "";


    return elemento.innerHTML;

}


/* ========================================================
   CERRAR SESIÓN
======================================================== */

function cerrarSesionAdmin() {

    localStorage.removeItem(
        "kimbos_admin_token"
    );


    usuarioAdmin = null;


    document.getElementById(
        "vistaPanel"
    ).classList.add(
        "d-none"
    );


    document.getElementById(
        "vistaLogin"
    ).classList.remove(
        "d-none"
    );


    document.getElementById(
        "formAdminLogin"
    ).reset();

}
/* ========================================================
   PRODUCTOS
======================================================== */

async function cargarProductosAdmin() {

    const cargando =
        document.getElementById(
            "cargandoProductosAdmin"
        );

    const lista =
        document.getElementById(
            "listaProductosAdmin"
        );


    cargando.classList.remove(
        "d-none"
    );

    lista.innerHTML = "";


    try {

        const respuesta =
            await fetch(
                "/api/catalogo"
            );


        const datos =
            await respuesta.json();


        cargando.classList.add(
            "d-none"
        );


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            throw new Error(
                "No se pudieron cargar los productos."
            );

        }


        catalogoAdmin =
            datos.categorias;


        llenarCategoriasProducto();


        renderizarProductosAdmin();


    } catch (error) {

        cargando.classList.add(
            "d-none"
        );


        lista.innerHTML = `
            <div class="alert alert-danger">
                ${error.message}
            </div>
        `;

    }

}
function renderizarProductosAdmin() {

    const lista =
        document.getElementById(
            "listaProductosAdmin"
        );


    lista.innerHTML = "";


    let cantidadProductos =
        0;


    catalogoAdmin.forEach(
        categoria => {

            categoria.productos.forEach(
                producto => {

                    cantidadProductos++;


                    const estado =
                        producto.disponible
                            ? `
                                <span class="estado-disponible">
                                    ● Disponible
                                </span>
                            `
                            : `
                                <span class="estado-agotado">
                                    ● Agotado
                                </span>
                            `;


                    const botonDisponibilidad =
                        producto.disponible
                            ? `
                                <button
                                    class="
                                        btn-disponibilidad
                                        btn-marcar-agotado
                                    "
                                    onclick="
                                        cambiarDisponibilidadProducto(
                                            ${producto.id},
                                            false
                                        )
                                    "
                                >
                                    Marcar agotado
                                </button>
                            `
                            : `
                                <button
                                    class="
                                        btn-disponibilidad
                                        btn-marcar-disponible
                                    "
                                    onclick="
                                        cambiarDisponibilidadProducto(
                                            ${producto.id},
                                            true
                                        )
                                    "
                                >
                                    Marcar disponible
                                </button>
                            `;


                    lista.innerHTML += `
                        <div class="producto-gestion">

                            <div>

                                <small class="text-secondary">
                                    ${escaparHtmlAdmin(
                                        categoria.nombre
                                    )}
                                </small>


                                <h6>
                                    ${escaparHtmlAdmin(
                                        producto.nombre
                                    )}
                                </h6>


                                <div class="text-secondary small">
                                    ${escaparHtmlAdmin(
                                        producto.descripcion ||
                                        "Sin descripción"
                                    )}
                                </div>


                                <div class="mt-2">

                                    <span class="producto-precio-admin">
                                        S/
                                        ${Number(
                                            producto.precio
                                        ).toFixed(2)}
                                    </span>

                                    <span class="text-secondary ms-2">
                                        ⏱
                                        ${producto.tiempo_preparacion_min}
                                        min
                                    </span>

                                </div>


                                <div class="mt-2">
                                    ${estado}
                                </div>

                            </div>


                            <div class="acciones-producto">

                                ${botonDisponibilidad}


                                ${
                                    usuarioAdmin &&
                                    usuarioAdmin.rol === "ADMIN"
                                        ? `
                                            <button
                                                class="btn-editar-producto"
                                                onclick="
                                                    editarProductoAdmin(
                                                        ${producto.id}
                                                    )
                                                "
                                            >
                                                ✏ Editar
                                            </button>


                                            <button
                                                class="btn-desactivar-producto"
                                                onclick="
                                                    desactivarProductoAdmin(
                                                        ${producto.id}
                                                    )
                                                "
                                            >
                                                Desactivar
                                            </button>
                                        `
                                        : ""
                                }

                            </div>

                        </div>
                    `;

                }
            );

        }
    );


    if (cantidadProductos === 0) {

        lista.innerHTML = `
            <div class="text-center py-5">

                <div style="font-size: 3rem;">
                    🍔
                </div>

                <h5 class="mt-3">
                    No existen productos
                </h5>

            </div>
        `;

    }

}
async function cambiarDisponibilidadProducto(
    productoId,
    disponible
) {

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    try {

        const respuesta =
            await fetch(
                `/api/catalogo/productos/${productoId}/disponibilidad`,
                {
                    method: "PATCH",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Authorization":
                            `Bearer ${token}`
                    },

                    body:
                        JSON.stringify({
                            disponible
                        })
                }
            );


        const datos =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            alert(
                datos.mensaje ||
                "No se pudo cambiar la disponibilidad."
            );

            return;

        }


        await cargarProductosAdmin();


    } catch (error) {

        console.error(error);

        alert(
            "No se pudo conectar con el servidor."
        );

    }

}
function llenarCategoriasProducto() {

    const select =
        document.getElementById(
            "productoCategoria"
        );


    select.innerHTML = "";


    catalogoAdmin.forEach(
        categoria => {

            select.innerHTML += `
                <option value="${categoria.id}">
                    ${escaparHtmlAdmin(
                        categoria.nombre
                    )}
                </option>
            `;

        }
    );

}
function abrirNuevoProducto() {

    document.getElementById(
        "productoId"
    ).value = "";


    document.getElementById(
        "tituloFormularioProducto"
    ).textContent =
        "Nuevo producto";


    document.getElementById(
        "productoNombre"
    ).value = "";


    document.getElementById(
        "productoDescripcion"
    ).value = "";


    document.getElementById(
        "productoPrecio"
    ).value = "";


    document.getElementById(
        "productoPreparacion"
    ).value = 15;


    document.getElementById(
        "productoImagen"
    ).value = "";


    document.getElementById(
        "panelFormularioProducto"
    ).classList.remove(
        "d-none"
    );

}
function editarProductoAdmin(
    productoId
) {

    let productoEncontrado =
        null;

    let categoriaEncontrada =
        null;


    catalogoAdmin.forEach(
        categoria => {

            const producto =
                categoria.productos.find(
                    p =>
                        p.id === productoId
                );


            if (producto) {

                productoEncontrado =
                    producto;

                categoriaEncontrada =
                    categoria;

            }

        }
    );


    if (!productoEncontrado) {
        return;
    }


    document.getElementById(
        "productoId"
    ).value =
        productoEncontrado.id;


    document.getElementById(
        "tituloFormularioProducto"
    ).textContent =
        "Editar producto";


    document.getElementById(
        "productoNombre"
    ).value =
        productoEncontrado.nombre;


    document.getElementById(
        "productoDescripcion"
    ).value =
        productoEncontrado.descripcion || "";


    document.getElementById(
        "productoCategoria"
    ).value =
        categoriaEncontrada.id;


    document.getElementById(
        "productoPrecio"
    ).value =
        productoEncontrado.precio;


    document.getElementById(
        "productoPreparacion"
    ).value =
        productoEncontrado.tiempo_preparacion_min;


    document.getElementById(
        "productoImagen"
    ).value =
        productoEncontrado.imagen_url || "";


    document.getElementById(
        "panelFormularioProducto"
    ).classList.remove(
        "d-none"
    );


    document.getElementById(
        "panelFormularioProducto"
    ).scrollIntoView({
        behavior: "smooth"
    });

}
function cerrarFormularioProducto() {

    document.getElementById(
        "panelFormularioProducto"
    ).classList.add(
        "d-none"
    );

}
async function guardarProductoAdmin() {

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    const productoId =
        document.getElementById(
            "productoId"
        ).value;


    const datos = {

        categoria_id:
            Number(
                document.getElementById(
                    "productoCategoria"
                ).value
            ),

        nombre:
            document.getElementById(
                "productoNombre"
            ).value.trim(),

        descripcion:
            document.getElementById(
                "productoDescripcion"
            ).value.trim(),

        precio:
            Number(
                document.getElementById(
                    "productoPrecio"
                ).value
            ),

        tiempo_preparacion_min:
            Number(
                document.getElementById(
                    "productoPreparacion"
                ).value
            ),

        imagen_url:
            document.getElementById(
                "productoImagen"
            ).value.trim()
    };


    if (!datos.nombre) {

        alert(
            "Ingresa el nombre del producto."
        );

        return;

    }


    if (
        !Number.isFinite(datos.precio) ||
        datos.precio < 0
    ) {

        alert(
            "Ingresa un precio válido."
        );

        return;

    }


    const editando =
        productoId !== "";


    const url =
        editando
            ? `/api/catalogo/productos/${productoId}`
            : "/api/catalogo/productos";


    const metodo =
        editando
            ? "PATCH"
            : "POST";


    try {

        const respuesta =
            await fetch(
                url,
                {
                    method:
                        metodo,

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Authorization":
                            `Bearer ${token}`
                    },

                    body:
                        JSON.stringify(
                            datos
                        )
                }
            );


        const resultado =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !resultado.ok
        ) {

            alert(
                resultado.mensaje ||
                "No se pudo guardar el producto."
            );

            return;

        }


        cerrarFormularioProducto();


        await cargarProductosAdmin();


    } catch (error) {

        console.error(error);

        alert(
            "No se pudo conectar con el servidor."
        );

    }

}
function mostrarNuevaCategoria() {

    document.getElementById(
        "panelNuevaCategoria"
    ).classList.remove(
        "d-none"
    );

}


function ocultarNuevaCategoria() {

    document.getElementById(
        "panelNuevaCategoria"
    ).classList.add(
        "d-none"
    );

}
async function guardarCategoriaAdmin() {

    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    const nombre =
        document.getElementById(
            "categoriaNombre"
        ).value.trim();


    if (!nombre) {

        alert(
            "Ingresa el nombre de la categoría."
        );

        return;

    }


    const datos = {

        nombre,

        descripcion:
            document.getElementById(
                "categoriaDescripcion"
            ).value.trim(),

        orden:
            Number(
                document.getElementById(
                    "categoriaOrden"
                ).value
            ) || 0
    };


    try {

        const respuesta =
            await fetch(
                "/api/catalogo/categorias",
                {
                    method:
                        "POST",

                    headers: {
                        "Content-Type":
                            "application/json",

                        "Authorization":
                            `Bearer ${token}`
                    },

                    body:
                        JSON.stringify(
                            datos
                        )
                }
            );


        const resultado =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !resultado.ok
        ) {

            alert(
                resultado.mensaje ||
                "No se pudo crear la categoría."
            );

            return;

        }


        document.getElementById(
            "categoriaNombre"
        ).value = "";


        document.getElementById(
            "categoriaDescripcion"
        ).value = "";


        ocultarNuevaCategoria();


        await cargarProductosAdmin();


    } catch (error) {

        console.error(error);

        alert(
            "No se pudo conectar con el servidor."
        );

    }

}
async function desactivarProductoAdmin(
    productoId
) {

    const confirmar =
        confirm(
            "¿Deseas desactivar este producto? Ya no aparecerá en el menú del cliente."
        );


    if (!confirmar) {
        return;
    }


    const token =
        localStorage.getItem(
            "kimbos_admin_token"
        );


    try {

        const respuesta =
            await fetch(
                `/api/catalogo/productos/${productoId}/desactivar`,
                {
                    method:
                        "PATCH",

                    headers: {
                        "Authorization":
                            `Bearer ${token}`
                    }
                }
            );


        const datos =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            alert(
                datos.mensaje ||
                "No se pudo desactivar el producto."
            );

            return;

        }


        await cargarProductosAdmin();


    } catch (error) {

        console.error(error);

        alert(
            "No se pudo conectar con el servidor."
        );

    }

}



/* ========================================================
   SISTEMA MULTIAGENTE: ALERTA DE PEDIDO EN RIESGO
======================================================== */

const ACCIONES_AGENTES = {
    PRIORIZAR_PREPARACION: "Priorizar la preparación",
    ASIGNAR_REPARTIDOR_EXTRA: "Asignar un repartidor extra",
    AJUSTAR_TIEMPO_ESTIMADO: "Ajustar el tiempo estimado",
    MONITOREAR: "Monitorear"
};


function htmlAlertaAgentes(pedido) {

    const alerta = pedido.alerta;

    // Sin prediccion ML no hay nada que analizar.
    if (!pedido.prediccion_ml) {
        return "";
    }

    const enCurso =
        pedido.estado?.codigo !== "ENTREGADO" &&
        pedido.estado?.codigo !== "CANCELADO";

    const boton = enCurso
        ? `
            <button
                class="btn btn-sm btn-outline-dark mt-2"
                onclick="analizarPedidoConAgentes(${pedido.id}, this)"
            >
                🤖 ${alerta ? "Volver a analizar" : "Analizar con agentes"}
            </button>
        `
        : "";

    if (!alerta) {
        return enCurso ? `<div class="mb-3">${boton}</div>` : "";
    }

    if (alerta.estado === "PROCESANDO") {
        return `
            <div class="alerta-agentes">
                <div class="alerta-agentes-titulo">🤖 Agentes analizando el pedido…</div>
            </div>
        `;
    }

    if (alerta.estado === "ERROR") {
        return `
            <div class="alerta-agentes">
                <div class="alerta-agentes-titulo">🤖 Los agentes no pudieron analizar el pedido</div>
                ${boton}
            </div>
        `;
    }

    const factores = (alerta.factores || [])
        .map((factor) => `<span class="ma-chip">${escaparHtmlAdmin(factor)}</span>`)
        .join("");

    const nivel = (alerta.nivel || "").toUpperCase();

    const NIVEL = {
        ALTO: ["⛔", "Riesgo alto"],
        MEDIO: ["⚠️", "Riesgo medio"],
        BAJO: ["✅", "Riesgo bajo"]
    };

    const [iconoNivel, textoNivel] = NIVEL[nivel] || ["ℹ️", `Riesgo ${nivel || "--"}`];

    const prob = pedido.prediccion_ml?.probabilidad_porcentaje;

    return `
        <div class="ma-caja ma-${nivel.toLowerCase()}">

            <div class="ma-cabecera">
                <div>
                    <div class="ma-titulo">🤖 Análisis multiagente</div>
                    <div class="ma-subtitulo">
                        ${alerta.origen === "MANUAL" ? "Análisis manual" : "Automático al crear el pedido"}
                        · 3 agentes en cadena
                    </div>
                </div>
                <div class="ma-nivel">
                    <span>${iconoNivel} ${textoNivel}</span>
                    ${prob !== undefined && prob !== null ? `<small>${Number(prob).toFixed(1)} % según el modelo ML</small>` : ""}
                </div>
            </div>

            <ol class="ma-linea">

                <li class="ma-paso">
                    <span class="ma-icono">🔍</span>
                    <div class="ma-cuerpo">
                        <div class="ma-rol">1 · Agente Analista <span>· encuentra la causa</span></div>
                        <div class="ma-texto">${escaparHtmlAdmin(alerta.causa)}</div>
                        ${factores ? `<div class="ma-chips">${factores}</div>` : ""}
                    </div>
                </li>

                <li class="ma-paso">
                    <span class="ma-icono">⚙️</span>
                    <div class="ma-cuerpo">
                        <div class="ma-rol">2 · Agente de Operaciones <span>· decide la acción</span></div>
                        <div class="ma-accion">
                            ${escaparHtmlAdmin(ACCIONES_AGENTES[alerta.accion] || alerta.accion)}
                            ${alerta.minutos_extra ? `<span class="ma-min">+${alerta.minutos_extra} min</span>` : ""}
                        </div>
                        <div class="ma-texto ma-secundario">${escaparHtmlAdmin(alerta.justificacion)}</div>
                    </div>
                </li>

                <li class="ma-paso">
                    <span class="ma-icono">💬</span>
                    <div class="ma-cuerpo">
                        <div class="ma-rol">3 · Agente Comunicador <span>· avisa al cliente</span></div>
                        <div class="ma-mensaje">“${escaparHtmlAdmin(alerta.mensaje_cliente)}”</div>
                        <div class="ma-texto ma-secundario">Para el admin: ${escaparHtmlAdmin(alerta.resumen_admin)}</div>
                    </div>
                </li>

            </ol>

            ${boton}
        </div>
    `;
}


async function analizarPedidoConAgentes(pedidoId, boton) {

    const token = localStorage.getItem("kimbos_admin_token");

    boton.disabled = true;
    boton.textContent = "🤖 Analizando (≈15 s)…";

    try {

        const respuesta = await fetch(
            `/api/automatizacion/pedidos/${pedidoId}/alerta`,
            {
                method: "POST",
                headers: { "Authorization": `Bearer ${token}` }
            }
        );

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo analizar el pedido.");
        }

        await cargarPedidosAdmin();

    } catch (error) {

        alert(error.message);
        boton.disabled = false;
        boton.textContent = "🤖 Analizar con agentes";
    }
}



/* ========================================================
   REPARTIDORES
   El admin registra a los repartidores, marca quién está en
   turno y confirma a quién se asigna cada pedido (el sistema
   sugiere al que está en turno con menos pedidos activos).
======================================================== */

let repartidoresAdmin = [];
let repartidorSugeridoId = null;

const VEHICULOS_REPARTIDOR = {
    MOTO: "🛵 Moto",
    BICICLETA: "🚲 Bicicleta",
    AUTO: "🚗 Auto",
    CAMIONETA: "🚐 Camioneta",
    OTRO: "Otro"
};


async function cargarRepartidoresAdmin() {

    try {

        const respuesta = await fetch("/api/repartidores", {
            headers: {
                "Authorization": `Bearer ${localStorage.getItem("kimbos_admin_token")}`
            }
        });

        const datos = await respuesta.json();

        if (respuesta.ok && datos.ok) {
            repartidoresAdmin = datos.repartidores;
            repartidorSugeridoId = datos.sugerido_id;
        }

    } catch (error) {
        console.error(error);
    }
}


function cuerpoCambioEstado(pedidoId, nuevoEstado) {

    const cuerpo = { estado: nuevoEstado };

    const selector = document.getElementById(`repartidorPedido${pedidoId}`);

    if (nuevoEstado === "EN_RUTA" && selector) {
        cuerpo.repartidor_id = selector.value ? Number(selector.value) : null;
    }

    return cuerpo;
}


function htmlRepartidorPedido(pedido) {

    // Ya tiene repartidor: se muestra quién lo lleva.
    if (pedido.repartidor) {
        return `
            <div class="repartidor-pedido">
                ${VEHICULOS_REPARTIDOR[pedido.repartidor.tipo_vehiculo] || "🛵"}
                <strong>${escaparHtmlAdmin(pedido.repartidor.nombre)}</strong>
                ${pedido.repartidor.telefono ? `· ${escaparHtmlAdmin(pedido.repartidor.telefono)}` : ""}
            </div>
        `;
    }

    // Solo al enviar (PREPARANDO → EN_RUTA) se elige el repartidor.
    if (pedido.estado?.codigo !== "PREPARANDO") {
        return "";
    }

    const activos = repartidoresAdmin.filter((r) => r.activo);

    if (!activos.length) {
        return `
            <div class="repartidor-pedido text-secondary">
                Sin repartidores registrados: el pedido se enviará sin asignar.
            </div>
        `;
    }

    const opciones = activos
        .map((r) => `
            <option value="${r.id}" ${r.id === repartidorSugeridoId ? "selected" : ""}>
                ${escaparHtmlAdmin(r.nombre)}
                ${r.en_turno ? "" : "(fuera de turno)"}
                · ${r.pedidos_activos} en ruta
                ${r.id === repartidorSugeridoId ? "· sugerido ⭐" : ""}
            </option>
        `)
        .join("");

    return `
        <div class="repartidor-pedido">
            <label class="form-label small fw-bold mb-1" for="repartidorPedido${pedido.id}">
                🛵 Repartidor que llevará el pedido
            </label>
            <select id="repartidorPedido${pedido.id}" class="form-select form-select-sm">
                ${repartidorSugeridoId ? "" : `<option value="">Selecciona un repartidor</option>`}
                ${opciones}
            </select>
        </div>
    `;
}


function renderizarRepartidoresModal() {

    const contenedor = document.getElementById("listaRepartidores");

    if (!contenedor) {
        return;
    }

    // Selector del formulario de acceso
    const selectorAcceso = document.getElementById("accesoRepartidor");

    if (selectorAcceso) {
        selectorAcceso.innerHTML = repartidoresAdmin
            .filter((r) => r.activo)
            .map((r) => `<option value="${r.id}">${escaparHtmlAdmin(r.nombre)} (${escaparHtmlAdmin(r.codigo)})</option>`)
            .join("");
    }

    const esAdmin = usuarioAdmin && usuarioAdmin.rol === "ADMIN";

    if (!repartidoresAdmin.length) {
        contenedor.innerHTML = `
            <p class="text-secondary">Aún no hay repartidores registrados.</p>
        `;
        return;
    }

    const enTurno = repartidoresAdmin.filter((r) => r.activo && r.en_turno).length;

    contenedor.innerHTML = `
        <p class="small text-secondary mb-2">
            En turno: <strong>${enTurno}</strong>. El modelo ML usa este número para calcular la carga por repartidor.
        </p>

        <div class="table-responsive">
            <table class="table table-sm align-middle">
                <thead>
                    <tr>
                        <th>Código</th><th>Nombre</th><th>Teléfono</th><th>Vehículo</th>
                        <th>Acceso al panel</th><th>En ruta</th><th>Entregas hoy</th><th>En turno</th>
                        ${esAdmin ? "<th>Activo</th>" : ""}
                    </tr>
                </thead>
                <tbody>
                    ${repartidoresAdmin.map((r) => `
                        <tr class="${r.activo ? "" : "text-secondary"}">
                            <td>${escaparHtmlAdmin(r.codigo)}</td>
                            <td><strong>${escaparHtmlAdmin(r.nombre)}</strong></td>
                            <td>${escaparHtmlAdmin(r.telefono || "-")}</td>
                            <td>${VEHICULOS_REPARTIDOR[r.tipo_vehiculo] || r.tipo_vehiculo} ${escaparHtmlAdmin(r.placa || "")}</td>
                            <td>${r.correo_acceso
                                ? `✅ <small>${escaparHtmlAdmin(r.correo_acceso)}</small>`
                                : `<span class="text-secondary small">Sin acceso</span>`}</td>
                            <td>${r.pedidos_activos}</td>
                            <td>${r.entregas_hoy}</td>
                            <td>
                                <div class="form-check form-switch m-0">
                                    <input class="form-check-input" type="checkbox"
                                        ${r.en_turno ? "checked" : ""} ${r.activo ? "" : "disabled"}
                                        onchange="actualizarRepartidor(${r.id}, { en_turno: this.checked })">
                                </div>
                            </td>
                            ${esAdmin ? `
                                <td>
                                    <div class="form-check form-switch m-0">
                                        <input class="form-check-input" type="checkbox"
                                            ${r.activo ? "checked" : ""}
                                            onchange="actualizarRepartidor(${r.id}, { activo: this.checked })">
                                    </div>
                                </td>
                            ` : ""}
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}


async function actualizarRepartidor(repartidorId, cambios) {

    try {

        const respuesta = await fetch(`/api/repartidores/${repartidorId}`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${localStorage.getItem("kimbos_admin_token")}`
            },
            body: JSON.stringify(cambios)
        });

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo actualizar el repartidor.");
        }

    } catch (error) {
        alert(error.message);
    }

    await cargarRepartidoresAdmin();
    renderizarRepartidoresModal();
    await cargarPedidosAdmin();
}


async function registrarRepartidor(evento) {

    evento.preventDefault();

    const formulario = evento.target;
    const boton = formulario.querySelector("button[type=submit]");

    boton.disabled = true;

    try {

        const respuesta = await fetch("/api/repartidores", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${localStorage.getItem("kimbos_admin_token")}`
            },
            body: JSON.stringify({
                nombre: formulario.nombre.value,
                telefono: formulario.telefono.value,
                tipo_vehiculo: formulario.tipo_vehiculo.value,
                placa: formulario.placa.value
            })
        });

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo registrar el repartidor.");
        }

        formulario.reset();

        await cargarRepartidoresAdmin();
        renderizarRepartidoresModal();
        await cargarPedidosAdmin();

    } catch (error) {
        alert(error.message);
    } finally {
        boton.disabled = false;
    }
}


document.addEventListener("DOMContentLoaded", () => {

    const modal = document.getElementById("modalRepartidores");
    const formulario = document.getElementById("formRepartidor");

    if (modal) {
        modal.addEventListener("show.bs.modal", async () => {

            // El registro solo lo hace el ADMIN
            if (formulario) {
                formulario.classList.toggle(
                    "d-none",
                    !(usuarioAdmin && usuarioAdmin.rol === "ADMIN")
                );
            }

            await cargarRepartidoresAdmin();
            renderizarRepartidoresModal();
        });
    }

    if (formulario) {
        formulario.addEventListener("submit", registrarRepartidor);
    }

    const formularioAcceso = document.getElementById("formAccesoRepartidor");

    if (modal && formularioAcceso) {
        modal.addEventListener("show.bs.modal", () => {
            formularioAcceso.classList.toggle(
                "d-none",
                !(usuarioAdmin && usuarioAdmin.rol === "ADMIN")
            );
        });

        formularioAcceso.addEventListener("submit", darAccesoRepartidor);
    }
});


async function darAccesoRepartidor(evento) {

    evento.preventDefault();

    const formulario = evento.target;
    const boton = formulario.querySelector("button[type=submit]");

    boton.disabled = true;

    try {

        const respuesta = await fetch(`/api/repartidores/${formulario.repartidor.value}/acceso`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${localStorage.getItem("kimbos_admin_token")}`
            },
            body: JSON.stringify({
                correo: formulario.correo.value,
                password: formulario.password.value
            })
        });

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo guardar el acceso.");
        }

        formulario.correo.value = "";
        formulario.password.value = "";

        alert(datos.mensaje);

        await cargarRepartidoresAdmin();
        renderizarRepartidoresModal();

    } catch (error) {
        alert(error.message);
    } finally {
        boton.disabled = false;
    }
}



/* ========================================================
   SEGUIMIENTO DE LA ENTREGA
   Con repartidor asignado, la entrega la marca él desde su
   panel (/repartidor). El admin ve el avance y el resultado.
======================================================== */

function minutosDesde(fechaIso) {

    if (!fechaIso) {
        return null;
    }

    return Math.max(Math.round((Date.now() - new Date(fechaIso).getTime()) / 60000), 0);
}


function seguimientoEntrega(pedido) {

    const repartidor = pedido.repartidor;
    const estado = pedido.estado?.codigo;

    if (!repartidor || (estado !== "EN_RUTA" && estado !== "ENTREGADO")) {
        return "";
    }

    const nombre = escaparHtmlAdmin(repartidor.nombre);

    if (estado === "EN_RUTA") {

        const transcurrido = minutosDesde(pedido.fecha_pedido);
        const prometido = pedido.tiempo_estimado_total_min;
        const restantes = prometido !== null && transcurrido !== null ? prometido - transcurrido : null;

        let tiempo = "";

        if (restantes !== null) {
            tiempo = restantes >= 0
                ? `<span class="seg-tiempo ${restantes <= 5 ? "seg-justo" : "seg-ok"}">${restantes <= 5 ? "⚠️" : "⏱️"} quedan ${restantes} min</span>`
                : `<span class="seg-tiempo seg-tarde">⛔ ${Math.abs(restantes)} min tarde</span>`;
        }

        return `
            <div class="seguimiento-entrega">
                <div class="seg-titulo">🛵 En camino con ${nombre}</div>
                <div class="seg-detalle">
                    Pedido hace ${transcurrido ?? "--"} min · prometido ${prometido ?? "--"} min ${tiempo}
                </div>
                <div class="seg-nota">${nombre} marcará la entrega desde su panel.</div>
            </div>
        `;
    }

    const hora = pedido.fecha_entrega
        ? new Date(pedido.fecha_entrega).toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" })
        : "--";

    const real = pedido.resultado_real?.duracion_real_min;
    const conRetraso = pedido.resultado_real?.retraso;

    return `
        <div class="seguimiento-entrega seg-entregado">
            <div class="seg-titulo">✅ Entregado por ${nombre} a las ${hora}</div>
            <div class="seg-detalle">
                ${real !== undefined && real !== null ? `Tardó ${real} min · ` : ""}
                ${conRetraso === true
                    ? `<span class="seg-tiempo seg-tarde">⛔ con retraso</span>`
                    : conRetraso === false
                    ? `<span class="seg-tiempo seg-ok">✅ a tiempo</span>`
                    : ""}
            </div>
        </div>
    `;
}


/* El panel se actualiza solo cada 30 s para ver las entregas que
   marcan los repartidores (no mientras hay una ventana abierta). */
setInterval(() => {

    if (
        localStorage.getItem("kimbos_admin_token") &&
        !document.querySelector(".modal.show") &&
        document.visibilityState === "visible" &&
        !document.activeElement?.closest?.("#listaPedidosAdmin") &&
        typeof cargarPedidosAdmin === "function"
    ) {
        cargarPedidosAdmin(true);
    }

}, 30000);

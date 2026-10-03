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
            cargarPedidosAdmin
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

async function cargarPedidosAdmin() {

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


    cargando.classList.remove(
        "d-none"
    );


    lista.innerHTML = "";


    sinPedidos.classList.add(
        "d-none"
    );


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

        html += `
            <div class="alert alert-warning">
                No se encontró ml/metrics/metricas.json.
                Ejecuta el entrenamiento del modelo.
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
                        Reentrenando el modelo con el último pedido entregado...
                        (alrededor de 1 minuto; esta sección se actualiza sola)
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
                        puedeReentrenar
                            ? `
                                <button
                                    id="btnReentrenarML"
                                    class="btn btn-dark"
                                    type="button"
                                    onclick="reentrenarModeloML()"
                                    ${realesNuevos === 0 || estadoReentreno.en_curso ? "disabled" : ""}
                                >
                                    ↻ Reentrenar con datos actuales
                                </button>
                            `
                            : ""
                    }

                </div>

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
        boton.textContent = "↻ Reentrenar con datos actuales";

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


                    ${
                        accion.siguienteEstado
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
                        JSON.stringify({
                            estado:
                                nuevoEstado
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

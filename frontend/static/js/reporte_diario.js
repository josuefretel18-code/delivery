/* ========================================================
   REPORTE DIARIO (sistema multiagente)

   Pasos:  0 Datos (SQL) -> 1 Analista -> 2 Estratega -> 3 Redactor

   - El stepper de arriba funciona como pestañas: cada paso muestra
     solo lo que produjo ese agente ("Reporte completo" muestra todo).
   - "Generar reporte de hoy" llama a la API paso por paso, en orden,
     y muestra el estado de cada agente mientras trabaja.
   - La vista completa también se usa para exportar a PDF.

   Módulos de este archivo:
     1. Configuración y utilidades
     2. Componentes (chips, KPIs, tablas)
     3. Vistas por paso
     4. Stepper (pestañas + estados)
     5. Flujo secuencial de generación
     6. PDF, carga y eventos
======================================================== */

(function () {

    const modal = document.getElementById("modalReporteDiario");
    const contenido = document.getElementById("contenidoReporte");
    const selector = document.getElementById("selectorReporte");
    const botonGenerar = document.getElementById("btnGenerarReporte");
    const botonPdf = document.getElementById("btnPdfReporte");

    if (!modal) {
        return;
    }


    /* =====================================================
       1. CONFIGURACIÓN Y UTILIDADES
    ===================================================== */

    const PASOS = [
        { clave: "datos", num: 0, icono: "📊", nombre: "Datos del día", trabajando: "Recopilando datos del día…" },
        { clave: "analista", num: 1, icono: "🔍", nombre: "Analista de datos", trabajando: "Analizando datos…" },
        { clave: "estratega", num: 2, icono: "🧭", nombre: "Estratega", trabajando: "Generando estrategias…" },
        { clave: "redactor", num: 3, icono: "✍️", nombre: "Redactor", trabajando: "Redactando informe…" }
    ];

    const CALIFICACION = {
        BUENO: ["✅", "Día bueno", "ok"],
        REGULAR: ["⚠️", "Día regular", "aviso"],
        CRITICO: ["⛔", "Día crítico", "mal"]
    };

    const TIPO_HALLAZGO = {
        POSITIVO: ["✅", "Positivo", "ok"],
        ALERTA: ["⚠️", "Alerta", "aviso"],
        NEUTRO: ["ℹ️", "Neutro", "neutro"]
    };

    const PRIORIDAD = { ALTA: "mal", MEDIA: "aviso", BAJA: "neutro" };
    const NIVEL_RIESGO = { ALTO: "mal", MEDIO: "aviso", BAJO: "ok" };

    const RESPONSABLE = {
        ADMINISTRADOR: "Administrador",
        COCINA: "Cocina",
        REPARTIDORES: "Repartidores",
        ATENCION_AL_CLIENTE: "Atención al cliente"
    };

    const ACCIONES = {
        PRIORIZAR_PREPARACION: "Priorizar la preparación",
        ASIGNAR_REPARTIDOR_EXTRA: "Asignar un repartidor extra",
        AJUSTAR_TIEMPO_ESTIMADO: "Ajustar el tiempo estimado",
        MONITOREAR: "Monitorear"
    };

    let reportes = [];
    let reporteActual = null;
    let vista = "completo";          // "completo" o el número de paso (0-3)
    let generacion = null;           // { paso, estado: "trabajando" | "error", mensaje }


    function cabeceras() {
        return {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${localStorage.getItem("kimbos_admin_token")}`
        };
    }


    function escapar(valor) {

        return String(valor ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }


    function fechaCorta(iso) {
        const [anio, mes, dia] = iso.split("-");
        return `${dia}/${mes}/${anio}`;
    }


    function soles(valor) {
        return valor === null || valor === undefined ? "--" : `S/ ${Number(valor).toFixed(2)}`;
    }


    function porcentaje(valor) {
        return valor === null || valor === undefined ? "--" : `${valor} %`;
    }


    /* Reportes anteriores guardaban textos simples: se adaptan. */
    function normalizarHallazgo(h) {
        return typeof h === "string" ? { tipo: "NEUTRO", titulo: "", detalle: h } : h;
    }

    function normalizarRecomendacion(r) {
        return {
            titulo: r.titulo,
            accion: r.accion || r.detalle || "",
            responsable: r.responsable || null,
            horario: r.horario || "",
            meta: r.meta || "",
            prioridad: r.prioridad || "MEDIA"
        };
    }


    /* =====================================================
       2. COMPONENTES
    ===================================================== */

    /* Chip de color suave: tono = ok | aviso | mal | neutro */
    function chip(texto, tono = "neutro", icono = "") {
        return `<span class="rep-chip rep-chip-${tono}">${icono ? `${icono} ` : ""}${escapar(texto)}</span>`;
    }


    /* Comparación con badge: +S/ 110.06 vs ayer (verde si mejora) */
    function badgeComparacion(actual, referencia, etiqueta, { prefijo = "", decimales = 0, mejorSiSube = true } = {}) {

        if (actual === null || actual === undefined || referencia === null || referencia === undefined) {
            return "";
        }

        const cambio = Number(actual) - Number(referencia);

        if (Math.abs(cambio) < Math.pow(10, -decimales) / 2) {
            return chip(`= ${etiqueta}`, "neutro");
        }

        const valor = prefijo
            ? `${prefijo}${Math.abs(cambio).toFixed(decimales)}`
            : String(Number(Math.abs(cambio).toFixed(decimales)));

        const mejora = (cambio > 0) === mejorSiSube;

        return chip(`${cambio > 0 ? "▲ +" : "▼ −"}${valor} ${etiqueta}`, mejora ? "ok" : "mal");
    }


    function kpi(icono, titulo, valor, detalle = "", badges = "") {

        return `
            <div class="rep-kpi">
                <div class="rep-kpi-titulo">${icono} ${titulo}</div>
                <div class="rep-kpi-valor">${valor}</div>
                ${badges ? `<div class="rep-kpi-badges">${badges}</div>` : ""}
                ${detalle ? `<div class="rep-kpi-detalle">${detalle}</div>` : ""}
            </div>
        `;
    }


    function tabla(columnas, filas, vacio) {

        if (!filas.length) {
            return `<p class="rep-muted">${vacio}</p>`;
        }

        return `
            <div class="rep-tabla-envoltura">
                <table class="rep-tabla">
                    <thead><tr>${columnas.map((c) => `<th>${c}</th>`).join("")}</tr></thead>
                    <tbody>${filas.map((f) => `<tr>${f.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody>
                </table>
            </div>
        `;
    }


    function seccion(titulo, cuerpo, subtitulo = "") {

        return `
            <section class="rep-seccion">
                <h3>${titulo}</h3>
                ${subtitulo ? `<p class="rep-muted rep-subtitulo">${subtitulo}</p>` : ""}
                ${cuerpo}
            </section>
        `;
    }


    function esperandoAgente(paso) {

        const enCurso = generacion && generacion.paso === paso.num && generacion.estado === "trabajando";

        return `
            <div class="rep-espera">
                ${enCurso
                    ? `<span class="spinner-border spinner-border-sm"></span> ${paso.trabajando}`
                    : `${paso.icono} El ${paso.nombre} aún no ha trabajado en este reporte.`}
            </div>
        `;
    }


    /* =====================================================
       3. VISTAS POR PASO
    ===================================================== */

    /* Paso 0: indicadores del día (calculados con SQL) */
    function vistaDatos(r) {

        const m = r.metricas || {};
        const ml = m.modelo_ml || {};
        const ayer = (m.comparacion || {}).dia_anterior || {};
        const semana = (m.comparacion || {}).promedio_diario_7_dias_previos || {};

        const kpis = `
            <div class="rep-kpis">
                ${kpi("🧾", "Pedidos", m.pedidos ?? 0,
                    `${m.entregados ?? 0} entregados · ${m.cancelados ?? 0} cancelados`,
                    badgeComparacion(m.pedidos, ayer.pedidos, "vs ayer", { decimales: 1 }) +
                    badgeComparacion(m.pedidos, semana.pedidos, "vs prom. 7 días", { decimales: 1 }))}
                ${kpi("💰", "Ventas", soles(m.ventas_soles), "",
                    badgeComparacion(m.ventas_soles, ayer.ventas_soles, "vs ayer", { prefijo: "S/ ", decimales: 2 }) +
                    badgeComparacion(m.ventas_soles, semana.ventas_soles, "vs prom. 7 días", { prefijo: "S/ ", decimales: 2 }))}
                ${kpi("🧮", "Ticket promedio", soles(m.ticket_promedio_soles), "Gasto promedio por pedido")}
                ${kpi("⏱️", "Retrasos reales", porcentaje(m.porcentaje_retrasos),
                    `${m.entregas_con_retraso ?? 0} de ${m.entregas_evaluadas ?? 0} entregas · prometido ${m.tiempo_estimado_promedio_min ?? "--"} min, real ${m.tiempo_real_promedio_min ?? "--"} min`,
                    badgeComparacion(m.porcentaje_retrasos, ayer.porcentaje_retrasos, "pts vs ayer", { decimales: 1, mejorSiSube: false }))}
                ${kpi("🧠", "Acierto del modelo ML", porcentaje(ml.porcentaje_acierto),
                    `${ml.aciertos ?? 0} de ${ml.predicciones_evaluadas ?? 0} predicciones · riesgo prom. ${ml.riesgo_promedio_pct ?? "--"} %`)}
                ${kpi("🛵", "Repartidores para mañana", r.repartidores_sugeridos ?? "--",
                    `Hoy en turno: ${m.repartidores_disponibles ?? "--"}`,
                    r.franja_refuerzo ? chip(`Refuerzo ${r.franja_refuerzo}`, "aviso") : "")}
            </div>
        `;

        const horas = Object.entries(m.pedidos_por_hora || {});
        const maximo = Math.max(1, ...horas.map(([, n]) => n));

        const barras = horas.length
            ? horas.map(([hora, n]) => `
                <div class="rep-barra">
                    <span class="rep-barra-h">${escapar(hora)}</span>
                    <span class="rep-barra-f" style="width:${Math.round((n / maximo) * 70)}%"></span>
                    <span class="rep-num">${n}</span>
                </div>
            `).join("")
            : `<p class="rep-muted">Sin pedidos.</p>`;

        const productos = tabla(
            ["Producto", "Unidades"],
            (m.productos_mas_vendidos || []).map((p) => [escapar(p.producto), `<span class="rep-num">${p.unidades}</span>`]),
            "Sin ventas."
        );

        const repartidores = tabla(
            ["Repartidor", "Entregas", "Retrasos", "Tiempo real prom.", "Estado"],
            (m.entregas_por_repartidor || []).map((x) => [
                `<strong>${escapar(x.repartidor)}</strong>`,
                `<span class="rep-num">${x.entregas}</span>`,
                `<span class="rep-num">${x.retrasos}</span>`,
                `<span class="rep-num">${x.tiempo_real_promedio_min ?? "--"} min</span>`,
                x.retrasos ? chip(`${x.retrasos} con retraso`, "mal") : chip("Sin retrasos", "ok")
            ]),
            "Sin pedidos asignados a repartidores."
        );

        const alertas = tabla(
            ["Pedido", "Riesgo", "Acción recomendada", "Min. extra"],
            (m.alertas_detalle || []).map((a) => [
                escapar(a.pedido),
                chip(a.nivel, NIVEL_RIESGO[a.nivel] || "neutro"),
                escapar(ACCIONES[a.accion] || a.accion),
                `<span class="rep-num">${a.minutos_extra ?? 0}</span>`
            ]),
            "Los agentes no analizaron pedidos este día."
        );

        return `
            ${seccion("📊 Indicadores del día", kpis, "Calculados por el sistema con SQL; los agentes los interpretan.")}
            ${seccion("Operación del día", `
                <div class="rep-dos">
                    <div>
                        <div class="rep-etiqueta">Pedidos por hora${m.hora_pico ? ` · pico: ${escapar(m.hora_pico)}` : ""}</div>
                        ${barras}
                    </div>
                    <div>
                        <div class="rep-etiqueta">Productos más vendidos</div>
                        ${productos}
                    </div>
                </div>
            `)}
            ${seccion("🛵 Repartidores", repartidores)}
            ${seccion("⚠️ Alertas de riesgo (pedidos analizados por los agentes)", alertas)}
        `;
    }


    /* Paso 1: hallazgos del Agente Analista */
    function vistaAnalista(r) {

        if (r.etapa === null || r.etapa < 1) {
            return seccion("🔍 1 · Agente Analista de datos: hallazgos", esperandoAgente(PASOS[1]));
        }

        const hallazgos = (r.hallazgos || []).map(normalizarHallazgo).map((h) => {
            const [icono, etiqueta, tono] = TIPO_HALLAZGO[h.tipo] || TIPO_HALLAZGO.NEUTRO;
            return `
                <div class="rep-hallazgo rep-hallazgo-${tono}">
                    <div class="rep-hallazgo-cab">
                        ${chip(etiqueta, tono, icono)}
                        ${h.titulo ? `<strong>${escapar(h.titulo)}</strong>` : ""}
                    </div>
                    <div>${escapar(h.detalle)}</div>
                </div>
            `;
        }).join("");

        return seccion(
            "🔍 1 · Agente Analista de datos: hallazgos",
            `<div class="rep-hallazgos">${hallazgos || `<p class="rep-muted">Sin hallazgos.</p>`}</div>`,
            "Recibe los indicadores del día y devuelve hallazgos con cifras y comparaciones."
        );
    }


    /* Paso 2: plan del Agente Estratega */
    function vistaEstratega(r) {

        if (r.etapa === null || r.etapa < 2) {
            return seccion("🧭 2 · Agente Estratega: plan para mañana", esperandoAgente(PASOS[2]));
        }

        const plan = tabla(
            ["Prioridad", "Acción", "Responsable", "Horario", "Meta"],
            (r.recomendaciones || []).map(normalizarRecomendacion).map((x) => [
                chip(x.prioridad, PRIORIDAD[x.prioridad] || "neutro"),
                `<strong>${escapar(x.titulo)}</strong><div class="rep-muted">${escapar(x.accion)}</div>`,
                escapar(RESPONSABLE[x.responsable] || x.responsable || "--"),
                escapar(x.horario || "--"),
                escapar(x.meta || "--")
            ]),
            "Sin recomendaciones."
        );

        const refuerzo = `
            <div class="rep-refuerzo">
                🛵 <strong>${r.repartidores_sugeridos ?? "--"} repartidores</strong> sugeridos para mañana
                ${r.franja_refuerzo ? ` · reforzar de ${escapar(r.franja_refuerzo)}` : ""}
            </div>
        `;

        return seccion(
            "🧭 2 · Agente Estratega: plan para mañana",
            refuerzo + plan,
            "Recibe los hallazgos del Analista y propone acciones con responsable, horario y meta medible."
        );
    }


    /* Paso 3: resumen del Agente Redactor */
    function vistaRedactor(r) {

        if (r.etapa === null || r.etapa < 3 || !r.titulo) {
            return seccion("✍️ 3 · Agente Redactor: resumen ejecutivo", esperandoAgente(PASOS[3]));
        }

        const [icono, texto, tono] = CALIFICACION[r.calificacion] || ["", "", "neutro"];

        return `
            <div class="rep-resumen">
                <div class="rep-resumen-cab">
                    <span class="rep-resumen-etiqueta">✍️ 3 · Agente Redactor: resumen ejecutivo</span>
                    ${r.calificacion ? chip(texto, tono, icono) : ""}
                </div>
                <h2>${escapar(r.titulo)}</h2>
                <p class="mb-0">${escapar(r.resumen)}</p>
            </div>
            ${r.conclusion
                ? seccion("Conclusión y foco para mañana", `<div class="rep-conclusion">${escapar(r.conclusion)}</div>`)
                : ""}
        `;
    }


    function vistaCompleta(r) {

        // Orden de lectura: primero el resumen (lo que lee el jefe)
        return `
            ${vistaRedactor(r)}
            ${vistaDatos(r)}
            ${vistaAnalista(r)}
            ${vistaEstratega(r)}
        `;
    }


    function pie(r) {

        return `
            <div class="rep-pie">
                Kimbos Delivery · Reporte del ${fechaCorta(r.fecha)} ·
                ${r.origen === "PROGRAMADO" ? "Generado automáticamente (Cloud Scheduler)" : "Generado manualmente"}
                ${r.generado ? `el ${new Date(r.generado).toLocaleString("es-PE")}` : ""}
                · Sistema multiagente: Analista de datos → Estratega → Redactor
            </div>
        `;
    }


    /* =====================================================
       4. STEPPER (pestañas + estado de cada agente)
    ===================================================== */

    function estadoPaso(paso, r) {

        if (generacion && generacion.paso === paso.num) {
            return generacion.estado;                       // trabajando | error
        }

        const etapa = r ? r.etapa : null;

        if (etapa !== null && etapa !== undefined && etapa >= paso.num) {
            return "listo";
        }

        return "pendiente";
    }


    function textoEstado(paso, estado, r) {

        if (estado === "trabajando") return paso.trabajando;
        if (estado === "error") return generacion?.mensaje || "No se pudo completar";
        if (estado === "pendiente") return "En espera";

        const m = (r && r.metricas) || {};

        return {
            0: `${m.pedidos ?? 0} pedidos analizados`,
            1: `${(r.hallazgos || []).length} hallazgos`,
            2: `${(r.recomendaciones || []).length} acciones · ${r.repartidores_sugeridos ?? "--"} repartidores`,
            3: r.calificacion ? (CALIFICACION[r.calificacion] || [])[1] || "Resumen listo" : "Resumen listo"
        }[paso.num];
    }


    function htmlStepper(r) {

        const pasos = PASOS.map((paso, indice) => {

            const estado = estadoPaso(paso, r);

            const marca = {
                listo: "✓",
                trabajando: `<span class="spinner-border spinner-border-sm"></span>`,
                error: "!",
                pendiente: paso.num
            }[estado];

            return `
                ${indice ? `<span class="rep-paso-flecha" aria-hidden="true">→</span>` : ""}
                <button type="button" class="rep-paso rep-paso-${estado} ${vista === paso.num ? "activo" : ""}"
                    data-vista="${paso.num}" role="tab" aria-selected="${vista === paso.num}">
                    <span class="rep-paso-marca">${marca}</span>
                    <span class="rep-paso-cuerpo">
                        <span class="rep-paso-nombre">${paso.icono} ${paso.num} · ${paso.nombre}</span>
                        <span class="rep-paso-estado">${escapar(textoEstado(paso, estado, r))}</span>
                    </span>
                </button>
            `;
        }).join("");

        const reintento = generacion && generacion.estado === "error"
            ? `
                <div class="rep-reintento">
                    ${chip(`Paso ${generacion.paso}: ${generacion.mensaje}`, "mal", "⛔")}
                    <button type="button" class="btn btn-sm btn-dark" data-reintentar="${generacion.paso}">
                        Reintentar desde el paso ${generacion.paso}
                    </button>
                </div>
            `
            : (r && r.estado === "PROCESANDO" && !generacion)
                ? `
                    <div class="rep-reintento">
                        ${chip("Este reporte quedó a medias", "aviso", "⚠️")}
                        <button type="button" class="btn btn-sm btn-dark" data-reintentar="${(r.etapa ?? -1) + 1}">
                            Continuar desde el paso ${(r.etapa ?? -1) + 1}
                        </button>
                    </div>
                `
                : "";

        return `
            <div class="rep-stepper" role="tablist" aria-label="Pasos del reporte">
                <button type="button" class="rep-tab-completo ${vista === "completo" ? "activo" : ""}"
                    data-vista="completo" role="tab" aria-selected="${vista === "completo"}">
                    📄 Reporte completo
                </button>
                <div class="rep-pasos">${pasos}</div>
            </div>
            ${reintento}
        `;
    }


    /* =====================================================
       5. RENDER Y FLUJO SECUENCIAL
    ===================================================== */

    function pintar() {

        const r = reporteActual;

        botonPdf.disabled = !r || r.estado !== "LISTO" && r.estado !== "SIN_DATOS" || !!generacion;

        if (!r) {
            contenido.innerHTML = generacion
                ? `<div class="rep">${htmlStepper(null)}${esperandoAgente(PASOS[0])}</div>`
                : `
                    <div class="alert alert-light border">
                        Aún no hay reportes. Se generan solos cada día a las 23:00,
                        o puedes generar el de hoy con el botón.
                    </div>
                `;
            return;
        }

        if (r.estado === "SIN_DATOS") {
            contenido.innerHTML = `
                <div class="rep">
                    <div class="rep-resumen">
                        <h2>${escapar(r.titulo)}</h2>
                        <p class="mb-0">${escapar(r.resumen)} Los agentes no se ejecutaron (costo 0).</p>
                    </div>
                    ${pie(r)}
                </div>
            `;
            return;
        }

        const cuerpo = {
            completo: vistaCompleta,
            0: vistaDatos,
            1: vistaAnalista,
            2: vistaEstratega,
            3: vistaRedactor
        }[vista](r);

        contenido.innerHTML = `
            <div class="rep">
                ${htmlStepper(r)}
                ${r.estado === "ERROR" && !generacion
                    ? `<div class="alert alert-danger py-2">${escapar(r.error || "No se pudo completar el reporte.")}</div>`
                    : ""}
                <div class="rep-vista">${cuerpo}</div>
                ${pie(r)}
            </div>
        `;
    }


    async function llamarPaso(paso, fecha) {

        const respuesta = await fetch(`/api/automatizacion/reportes/pasos/${paso.clave}`, {
            method: "POST",
            headers: cabeceras(),
            body: JSON.stringify(fecha ? { fecha } : {})
        });

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo completar el paso.");
        }

        return datos.reporte;
    }


    /* Ejecuta los pasos en orden, uno por uno, desde "desde". */
    async function generarSecuencial(desde = 0) {

        botonGenerar.disabled = true;
        selector.disabled = true;

        let fecha = desde > 0 && reporteActual ? reporteActual.fecha : null;

        try {

            for (const paso of PASOS.filter((p) => p.num >= desde)) {

                generacion = { paso: paso.num, estado: "trabajando" };

                // Se enfoca la pestaña del agente que está trabajando
                vista = paso.num;
                pintar();

                reporteActual = await llamarPaso(paso, fecha);
                fecha = reporteActual.fecha;

                // Un dia sin pedidos termina aqui (sin usar el LLM)
                if (reporteActual.estado === "SIN_DATOS") {
                    break;
                }
            }

            generacion = null;
            vista = "completo";
            pintar();

            await cargarLista(fecha);

        } catch (error) {

            generacion = { ...generacion, estado: "error", mensaje: error.message };
            pintar();

        } finally {
            botonGenerar.disabled = false;
            selector.disabled = !reportes.length;
        }
    }


    /* =====================================================
       6. PDF, CARGA Y EVENTOS
    ===================================================== */

    function exportarPdf() {

        if (!reporteActual) {
            return;
        }

        const ventana = window.open("", "_blank");

        if (!ventana) {
            alert("Permite las ventanas emergentes de esta página para exportar el PDF.");
            return;
        }

        ventana.document.open();
        ventana.document.write(`<!doctype html>
            <html lang="es">
            <head>
                <meta charset="utf-8">
                <title>Reporte_Kimbos_${escapar(reporteActual.fecha)}</title>
                <style>
                    @page { size: A4; margin: 14mm; }
                    body { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; margin: 0; background: #fff; }
                    .marca { display: flex; justify-content: space-between; align-items: baseline;
                             border-bottom: 3px solid #ff6b00; padding-bottom: 8px; margin-bottom: 16px; }
                    .marca strong { font-size: 22px; letter-spacing: .04em; }
                    .marca span { color: #52514e; font-size: 12px; }
                    .rep-kpi, .rep-hallazgo, .rep-tabla tr, .rep-resumen, .rep-conclusion { break-inside: avoid; }
                    h3 { break-after: avoid; }
                    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                    ${ESTILOS}
                    .rep-kpis { grid-template-columns: repeat(3, 1fr) !important; }
                    .rep-dos { grid-template-columns: 1fr 1fr !important; }
                </style>
            </head>
            <body>
                <div class="marca">
                    <strong>KIMBOS</strong>
                    <span>Reporte diario del sistema multiagente · ${fechaCorta(reporteActual.fecha)}</span>
                </div>
                <div class="rep">${vistaCompleta(reporteActual)}${pie(reporteActual)}</div>
                <script>
                    window.onload = function () { setTimeout(function () { window.print(); }, 300); };
                <\/script>
            </body>
            </html>`);
        ventana.document.close();
    }


    function llenarSelector() {

        selector.innerHTML = reportes.length
            ? reportes.map((r, i) => `<option value="${i}">${fechaCorta(r.fecha)}</option>`).join("")
            : `<option>Sin reportes</option>`;

        selector.disabled = !reportes.length;
    }


    async function cargarLista(fechaElegida = null) {

        const respuesta = await fetch("/api/automatizacion/reportes", { headers: cabeceras() });
        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudieron cargar los reportes.");
        }

        reportes = datos.reportes;
        llenarSelector();

        const indice = Math.max(0, reportes.findIndex((r) => r.fecha === fechaElegida));
        selector.value = String(indice);
        reporteActual = reportes[indice] || null;
        pintar();
    }


    async function cargar() {

        if (generacion && generacion.estado === "trabajando") {
            pintar();
            return;
        }

        generacion = null;
        vista = "completo";
        contenido.innerHTML = `<p class="text-secondary">Cargando...</p>`;

        try {
            await cargarLista();
        } catch (error) {
            contenido.innerHTML = `<div class="alert alert-danger">${escapar(error.message)}</div>`;
        }
    }


    contenido.addEventListener("click", (evento) => {

        const pestana = evento.target.closest("[data-vista]");

        if (pestana) {
            const valor = pestana.dataset.vista;
            vista = valor === "completo" ? "completo" : Number(valor);
            pintar();
            return;
        }

        const reintentar = evento.target.closest("[data-reintentar]");

        if (reintentar) {
            generarSecuencial(Number(reintentar.dataset.reintentar));
        }
    });

    selector.addEventListener("change", () => {
        generacion = null;
        vista = "completo";
        reporteActual = reportes[Number(selector.value)];
        pintar();
    });

    botonGenerar.addEventListener("click", () => {
        reporteActual = null;
        generarSecuencial(0);
    });

    botonPdf.addEventListener("click", exportarPdf);
    modal.addEventListener("show.bs.modal", cargar);


    /* =====================================================
       ESTILOS (los mismos en pantalla y en el PDF)
    ===================================================== */

    const ESTILOS = `
        .rep { color: #0b0b0b; font-size: 14px; line-height: 1.5; }
        .rep h2 { font-size: 20px; font-weight: 700; margin: 4px 0 6px; }
        .rep h3 { font-size: 15px; font-weight: 700; margin: 0 0 8px; }
        .rep-muted { color: #52514e; font-size: 12.5px; }
        .rep-subtitulo { margin: -4px 0 10px; }
        .rep-seccion { margin-top: 22px; }
        .rep-etiqueta { font-size: 12px; font-weight: 700; color: #52514e; margin-bottom: 6px; }

        /* Chips de color suave */
        .rep-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 10px; border-radius: 999px;
                    font-size: 11.5px; font-weight: 600; white-space: nowrap; border: 1px solid; }
        .rep-chip-ok { background: #e9f7e9; border-color: #b9e2b9; color: #1d5e1d; }
        .rep-chip-aviso { background: #fff6dd; border-color: #f3d98f; color: #6b4d00; }
        .rep-chip-mal { background: #fdeaea; border-color: #f1b5b5; color: #8a1f1f; }
        .rep-chip-neutro { background: #f1f1ef; border-color: #deddd6; color: #52514e; }

        /* Stepper / pestañas */
        .rep-stepper { display: flex; flex-wrap: wrap; gap: 10px; align-items: stretch; margin-bottom: 14px; }
        .rep-tab-completo { border: 1px solid #e1e0d9; background: #fff; border-radius: 14px; padding: 10px 14px;
                            font-weight: 600; font-size: 13px; }
        .rep-tab-completo.activo { border-color: #171717; background: #171717; color: #fff; }
        .rep-pasos { flex: 1; display: flex; align-items: stretch; gap: 6px; min-width: 0; }
        .rep-paso { flex: 1; min-width: 0; display: flex; gap: 10px; align-items: center; text-align: left;
                    border: 1px solid #e1e0d9; border-radius: 14px; padding: 10px 12px; background: #fff;
                    transition: border-color .15s ease, box-shadow .15s ease; }
        .rep-paso:hover { border-color: #c3c2b7; }
        .rep-paso.activo { border-color: #ff6b00; box-shadow: 0 0 0 3px rgba(255, 107, 0, .12); }
        .rep-paso-marca { flex: none; width: 28px; height: 28px; border-radius: 50%; display: inline-flex;
                          align-items: center; justify-content: center; font-weight: 700; font-size: 12px;
                          background: #ececec; color: #171717; }
        .rep-paso-listo .rep-paso-marca { background: #1d8a1d; color: #fff; }
        .rep-paso-trabajando .rep-paso-marca { background: #fff6dd; color: #6b4d00; }
        .rep-paso-trabajando { border-color: #f3d98f; background: #fffcf2; }
        .rep-paso-error .rep-paso-marca { background: #d03b3b; color: #fff; }
        .rep-paso-error { border-color: #f1b5b5; background: #fff8f8; }
        .rep-paso-cuerpo { display: flex; flex-direction: column; min-width: 0; }
        .rep-paso-nombre { font-weight: 700; font-size: 12.5px; }
        .rep-paso-estado { font-size: 11.5px; color: #52514e; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .rep-paso-flecha { display: flex; align-items: center; color: #898781; }
        .rep-reintento { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: -4px 0 12px; }
        .rep-espera { padding: 18px; border-radius: 14px; border: 1px dashed #d8d8d8; background: #fff;
                      color: #52514e; display: flex; gap: 10px; align-items: center; }

        /* KPIs */
        .rep-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
        .rep-kpi { border: 1px solid #ecebe6; border-radius: 16px; padding: 14px 16px; background: #fff;
                   box-shadow: 0 1px 2px rgba(0, 0, 0, .03); }
        .rep-kpi-titulo { font-size: 12.5px; color: #52514e; font-weight: 600; }
        .rep-kpi-valor { font-size: 28px; font-weight: 800; letter-spacing: -.01em; line-height: 1.2; margin: 2px 0 6px;
                         font-variant-numeric: tabular-nums; }
        .rep-kpi-badges { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 6px; }
        .rep-kpi-detalle { font-size: 11.5px; color: #898781; }

        /* Hallazgos */
        .rep-hallazgos { display: grid; gap: 8px; }
        .rep-hallazgo { border: 1px solid #ecebe6; border-left-width: 4px; border-radius: 12px; padding: 10px 14px; background: #fff; }
        .rep-hallazgo-ok { border-left-color: #1d8a1d; }
        .rep-hallazgo-aviso { border-left-color: #e0a400; }
        .rep-hallazgo-neutro { border-left-color: #b5b4ad; }
        .rep-hallazgo-cab { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 4px; }

        /* Tablas */
        .rep-tabla-envoltura { overflow-x: auto; border: 1px solid #ecebe6; border-radius: 12px; background: #fff; }
        .rep-tabla { width: 100%; border-collapse: collapse; font-size: 12.5px; }
        .rep-tabla th { text-align: left; font-weight: 700; color: #52514e; background: #fafaf8;
                        border-bottom: 1px solid #ecebe6; padding: 8px 10px; }
        .rep-tabla td { border-bottom: 1px solid #f1f0ec; padding: 8px 10px; vertical-align: top; }
        .rep-tabla tr:last-child td { border-bottom: 0; }
        .rep-num { font-variant-numeric: tabular-nums; }
        .rep-refuerzo { margin-bottom: 10px; padding: 10px 14px; border-radius: 12px; background: #fff8f2; border: 1px solid #ffd2b0; }

        /* Resumen y conclusion */
        .rep-resumen { border-radius: 16px; padding: 16px 18px; background: #f5f3ff; border: 1px solid #d8d4f5; }
        .rep-resumen-cab { display: flex; justify-content: space-between; gap: 10px; align-items: center; }
        .rep-resumen-etiqueta { font-size: 12px; font-weight: 700; color: #5b4fc7; }
        .rep-conclusion { border-left: 4px solid #2a78d6; background: #f4f8fd; border-radius: 8px; padding: 12px 14px; }

        .rep-dos { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
        .rep-barra { display: flex; align-items: center; gap: 8px; font-size: 12px; margin: 3px 0; }
        .rep-barra-h { width: 34px; color: #52514e; font-variant-numeric: tabular-nums; }
        .rep-barra-f { height: 12px; border-radius: 0 4px 4px 0; background: #2a78d6; min-width: 2px; }
        .rep-pie { margin-top: 22px; padding-top: 10px; border-top: 1px solid #e1e0d9; font-size: 11px; color: #898781; }

        @media (max-width: 860px) {
            .rep-pasos { flex-direction: column; }
            .rep-paso-flecha { display: none; }
            .rep-kpis { grid-template-columns: repeat(2, 1fr); }
            .rep-dos { grid-template-columns: 1fr; }
        }
    `;

    const estilo = document.createElement("style");
    estilo.textContent = ESTILOS;
    document.head.appendChild(estilo);

})();

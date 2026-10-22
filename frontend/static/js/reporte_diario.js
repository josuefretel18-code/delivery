/* ========================================================
   AGENTES DE IA: CONSULTAS Y REPORTE DIARIO (sistema multiagente)

   Dos modos con el mismo stepper, vistas y PDF:
   - Consulta: el administrador pregunta y trabajan 5 agentes:
     0 Orquestador (entiende la pregunta y elige el periodo) ->
     1 Datos -> 2 Analista -> 3 Estratega -> 4 Redactor -> 5 Evaluador.
   - Reporte diario (automatico a las 23:00):

   Pasos:  0 Datos (SQL) -> 1 Orquestador -> 2 Analista -> 3 Estratega
           -> 4 Redactor -> 5 Evaluador (+ decisión del Orquestador)

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
    const formConsulta = document.getElementById("formConsulta");
    const campoPregunta = document.getElementById("preguntaAgentes");
    const botonPreguntar = document.getElementById("btnPreguntar");
    const subtitulo = document.getElementById("subtituloReporte");

    if (!modal) {
        return;
    }


    /* =====================================================
       1. CONFIGURACIÓN Y UTILIDADES
    ===================================================== */

    const PASOS_REPORTE = [
        { clave: "datos", num: 0, icono: "📊", nombre: "Datos del día", trabajando: "Recopilando datos del día…" },
        { clave: "orquestador", num: 1, icono: "🧭", nombre: "Orquestador", trabajando: "Planificando el trabajo…" },
        { clave: "analista", num: 2, icono: "🔍", nombre: "Analista de datos", trabajando: "Analizando datos…" },
        { clave: "estratega", num: 3, icono: "🎯", nombre: "Estratega", trabajando: "Generando estrategias…" },
        { clave: "redactor", num: 4, icono: "✍️", nombre: "Redactor", trabajando: "Redactando informe…" },
        { clave: "evaluador", num: 5, icono: "⭐", nombre: "Evaluador", trabajando: "Calificando a los agentes…" }
    ];

    // En una consulta el Orquestador va primero: entiende la pregunta y
    // elige el periodo que luego se consulta.
    const PASOS_CONSULTA = [
        { clave: "orquestador", num: 0, icono: "🧭", nombre: "Orquestador", trabajando: "Entendiendo la pregunta…" },
        { clave: "datos", num: 1, icono: "📊", nombre: "Datos del periodo", trabajando: "Calculando los datos…" },
        { clave: "analista", num: 2, icono: "🔍", nombre: "Analista de datos", trabajando: "Analizando datos…" },
        { clave: "estratega", num: 3, icono: "🎯", nombre: "Estratega", trabajando: "Generando estrategias…" },
        { clave: "redactor", num: 4, icono: "✍️", nombre: "Redactor", trabajando: "Redactando la respuesta…" },
        { clave: "evaluador", num: 5, icono: "⭐", nombre: "Evaluador", trabajando: "Calificando a los agentes…" }
    ];

    let modo = "consulta";            // "consulta" o "reporte"
    let PASOS = PASOS_CONSULTA;

    const pasoDe = (clave) => PASOS.find((p) => p.clave === clave);
    const esConsulta = (r) => r && r.tipo === "CONSULTA";

    const NOMBRE_AGENTE = {
        orquestador: "🧭 Orquestador",
        analista: "🔍 Analista",
        estratega: "🎯 Estratega",
        redactor: "✍️ Redactor",
        evaluador: "⭐ Evaluador"
    };

    const VEREDICTO = {
        APROBADO: ["✅", "Aprobado", "ok"],
        OBSERVADO: ["⚠️", "Observado", "aviso"],
        DESAPROBADO: ["⛔", "Desaprobado", "mal"]
    };

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
    let vista = "completo";          // "completo" o el número de paso (0-5)
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


    function tonoNota(nota) {
        return nota === null || nota === undefined ? "neutro" : nota >= 8 ? "ok" : nota >= 6 ? "aviso" : "mal";
    }


    /* Nota del Evaluador para un agente (chip junto al título) */
    function notaAgente(r, agente) {

        const nota = ((r.evaluacion || {}).agentes || []).find((a) => a.agente === agente);

        const corregido = ((r.orquestacion || {}).flujo || [])
            .some((p) => p.agente === agente && (p.detalle || "").startsWith("Reintento"));

        return (nota ? ` ${chip(`⭐ ${nota.nota.toFixed(1)}`, tonoNota(nota.nota))}` : "") +
            (corregido ? ` ${chip("↻ corregido", "neutro")}` : "");
    }


    /* Encargo que el Orquestador le dio a un agente */
    function encargoAgente(r, agente) {

        const texto = ((r.orquestacion || {}).plan || {})[`encargo_${agente}`];

        return texto ? `<div class="rep-encargo">🧭 Encargo del Orquestador: ${escapar(texto)}</div>` : "";
    }


    /* Recorrido real de los agentes con su tiempo */
    function recorrido(r) {

        const flujo = (r.orquestacion || {}).flujo || [];

        if (!flujo.length) {
            return "";
        }

        return `
            <div class="rep-flujo">
                ${flujo.map((p) => `<span title="${escapar(p.detalle || "")}">${NOMBRE_AGENTE[p.agente] || escapar(p.agente)}${p.ms ? ` <small>${(p.ms / 1000).toFixed(1)} s</small>` : ""}</span>`).join("<b>→</b>")}
            </div>
        `;
    }


    /* =====================================================
       3. VISTAS POR PASO
    ===================================================== */

    /* Paso 0: indicadores del día (calculados con SQL) */
    function vistaDatos(r, { sinIndicadores = false } = {}) {

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
            ${sinIndicadores ? "" : seccion("📊 Indicadores del día", kpis, "Calculados por el sistema con SQL; los agentes los interpretan.")}
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

        if (r.etapa === null || r.etapa < pasoDe("analista").num) {
            return seccion("🔍 2 · Agente Analista de datos: hallazgos", esperandoAgente(pasoDe("analista")));
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
            "🔍 2 · Agente Analista de datos: hallazgos" + notaAgente(r, "analista"),
            encargoAgente(r, "analista") +
            `<div class="rep-hallazgos">${hallazgos || `<p class="rep-muted">Sin hallazgos.</p>`}</div>`,
            "Recibe los indicadores del día y devuelve hallazgos con cifras y comparaciones."
        );
    }


    /* Paso 2: plan del Agente Estratega */
    function vistaEstratega(r) {

        if (r.etapa === null || r.etapa < pasoDe("estratega").num) {
            return seccion("🎯 3 · Agente Estratega: plan para mañana", esperandoAgente(pasoDe("estratega")));
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
            "🎯 3 · Agente Estratega: plan para mañana" + notaAgente(r, "estratega"),
            encargoAgente(r, "estratega") + refuerzo + plan,
            "Recibe los hallazgos del Analista y propone acciones con responsable, horario y meta medible."
        );
    }


    /* Paso 3: resumen del Agente Redactor */
    function vistaRedactor(r) {

        if (r.etapa === null || r.etapa < pasoDe("redactor").num || !r.titulo) {
            return seccion("✍️ 4 · Agente Redactor: resumen ejecutivo", esperandoAgente(pasoDe("redactor")));
        }

        const [icono, texto, tono] = CALIFICACION[r.calificacion] || ["", "", "neutro"];

        return `
            <div class="rep-resumen">
                <div class="rep-resumen-cab">
                    <span class="rep-resumen-etiqueta">✍️ 4 · Agente Redactor: resumen ejecutivo${notaAgente(r, "redactor")}</span>
                    ${r.calificacion ? chip(texto, tono, icono) : ""}
                </div>
                ${encargoAgente(r, "redactor")}
                <h2>${escapar(r.titulo)}</h2>
                <p class="mb-0">${escapar(r.resumen)}</p>
            </div>
            ${puntosInforme(r)}
            ${r.conclusion
                ? seccion("Prioridad para mañana", `<div class="rep-conclusion">${escapar(r.conclusion)}</div>`)
                : ""}
            ${resumenSintetico(r) ? seccion("Resumen sintético del día", resumenSintetico(r)) : ""}
        `;
    }


    /* Resumen sintético del día: las cifras las calcula el sistema y
       el Agente Redactor escribe el estado y la lectura de cada una. */
    function resumenSintetico(r) {

        const rs = (r.metricas || {}).resumen_sintetico;

        if (!rs) {
            return "";
        }

        const lecturas = {};
        ((r.puntos || {}).resumen_sintetico || []).forEach((x) => { lecturas[x.indicador] = x; });

        const ESTADO = { BIEN: ["ok", "✅ Bien"], ATENCION: ["aviso", "⚠️ Atención"], CRITICO: ["mal", "⛔ Crítico"] };

        const caja = rs.diferencia_caja || {};
        const cancelacion = rs.tasa_cancelacion || {};
        const merma = rs.merma_y_empaques || {};

        const filas = [
            ["TICKET_PROMEDIO", "Ticket promedio", soles((rs.ticket_promedio || {}).valor_soles),
                (rs.ticket_promedio || {}).detalle || ""],
            ["DIFERENCIA_CAJA", "Diferencia de caja", soles(caja.valor_soles),
                `Vendido ${soles(caja.vendido_entregado_soles)} · cobrado ${soles(caja.cobrado_confirmado_soles)}` +
                (caja.pedidos_sin_confirmar ? ` · ${caja.pedidos_sin_confirmar} pago(s) por confirmar` : "")],
            ["TASA_CANCELACION", "Tasa de cancelación", porcentaje(cancelacion.valor_pct),
                `${cancelacion.cancelados ?? 0} de ${cancelacion.pedidos ?? 0} pedidos`],
            ["MERMA_Y_EMPAQUES", "Costo de merma y empaques", soles(merma.valor_soles),
                `Empaques ${soles(merma.empaques_soles)} (${merma.pedidos_preparados ?? 0} × ${soles(merma.costo_empaque_por_pedido_soles)}) · merma ${soles(merma.merma_soles)}`]
        ].map(([clave, nombre, valor, detalle]) => {

            const lectura = lecturas[clave];
            const [tono, etiqueta] = ESTADO[lectura?.estado] || ["neutro", "—"];

            return [
                `<strong>${nombre}</strong>`,
                `<span class="inf-res-valor">${valor}</span><div class="rep-muted">${escapar(detalle)}</div>`,
                lectura ? chip(etiqueta, tono) : "",
                escapar(lectura?.lectura || "")
            ];
        });

        return `
            ${tabla(["Indicador", "Resultado", "Estado", "Lectura"], filas, "")}
            ${merma.supuesto ? `<p class="rep-muted mt-2 mb-0">* ${escapar(merma.supuesto)}</p>` : ""}
        `;
    }


    /* "Lo que funcionó" y "A vigilar" del Redactor (en dos columnas) */
    function puntosInforme(r) {

        const p = r.puntos;

        if (!p || (!(p.lo_que_funciono || []).length && !(p.a_vigilar || []).length)) {
            return "";
        }

        const lista = (puntos) => `<ul>${(puntos || []).map((x) => `<li>${escapar(x)}</li>`).join("")}</ul>`;

        return `
            <div class="inf-puntos">
                <div class="inf-punto inf-punto-ok">
                    <div class="inf-punto-titulo">Lo que funcionó</div>
                    ${lista(p.lo_que_funciono)}
                </div>
                <div class="inf-punto inf-punto-aviso">
                    <div class="inf-punto-titulo">A vigilar</div>
                    ${lista(p.a_vigilar)}
                </div>
            </div>
        `;
    }


    const ANTES_DEL_ORQUESTADOR =
        `<p class="rep-muted">Este reporte se generó antes de incorporar al Orquestador y al Evaluador. Genéralo de nuevo para verlos.</p>`;


    /* Paso 1: plan del Agente Orquestador */
    function vistaOrquestador(r) {

        const titulo = `🧭 ${pasoDe("orquestador").num} · Agente Orquestador: ${esConsulta(r) ? "entiende la pregunta y reparte el trabajo" : "planifica y reparte el trabajo"}`;
        const o = r.orquestacion;

        if (!o || !o.plan) {
            return seccion(titulo, r.etapa !== null && r.etapa >= pasoDe("orquestador").num && r.estado !== "PROCESANDO"
                ? ANTES_DEL_ORQUESTADOR
                : esperandoAgente(pasoDe("orquestador")));
        }

        const p = o.plan;

        const encargos = tabla(
            ["Agente", "Encargo"],
            ["analista", "estratega", "redactor"].map((a) => [
                `<strong>${NOMBRE_AGENTE[a]}</strong>`,
                escapar(p[`encargo_${a}`] || "--")
            ]),
            ""
        );

        return seccion(
            titulo,
            `
                <div class="rep-orq">
                    <div><span class="rep-etiqueta">Enfoque del día</span><div class="rep-orq-enfoque">${escapar(p.enfoque || "--")}</div></div>
                    <div>${chip(`Prioridad ${p.prioridad || "--"}`, PRIORIDAD[p.prioridad] || "neutro")}</div>
                </div>
                ${esConsulta(r) && r.desde ? `<p class="mb-1"><strong>Periodo elegido:</strong> ${fechaCorta(r.desde)} al ${fechaCorta(r.hasta)}</p>` : ""}
                <p class="rep-muted mb-2">${escapar(p.razon || "")}</p>
                ${encargos}
            `,
            "Lee los indicadores, define el enfoque del día y le da un encargo a cada agente. Al final decide con la evaluación."
        );
    }


    /* Paso 5: notas del Agente Evaluador y decisión del Orquestador */
    function vistaEvaluador(r) {

        const titulo = "⭐ 5 · Agente Evaluador: calificación de los agentes";
        const e = r.evaluacion;

        if (!e) {
            return seccion(titulo, r.estado === "LISTO" ? ANTES_DEL_ORQUESTADOR : esperandoAgente(pasoDe("evaluador")));
        }

        const [icono, texto, tono] = VEREDICTO[e.veredicto] || ["", e.veredicto || "", "neutro"];
        const decision = (r.orquestacion || {}).decision || {};

        const notas = tabla(
            ["Agente", "Precisión", "Coherencia", "Utilidad", "Claridad", "Nota", "Observación"],
            (e.agentes || []).map((a) => [
                `<strong>${NOMBRE_AGENTE[a.agente] || escapar(a.agente)}</strong>`,
                `<span class="rep-num">${a.precision}</span>`,
                `<span class="rep-num">${a.coherencia}</span>`,
                `<span class="rep-num">${a.utilidad}</span>`,
                `<span class="rep-num">${a.claridad}</span>`,
                chip(a.nota.toFixed(1), tonoNota(a.nota)),
                `<span class="rep-muted">${escapar(a.observacion)}</span>`
            ]),
            ""
        );

        const cierre = `
            <div class="rep-decision">
                <strong>🧭 Decisión del Orquestador:</strong>
                ${decision.decision === "APROBAR" ? chip("Reporte aprobado", "ok", "✅") : chip(decision.decision || "--", "neutro")}
                ${decision.agente_reintento && decision.agente_reintento !== "ninguno"
                    ? chip(`Devolvió el trabajo a ${NOMBRE_AGENTE[decision.agente_reintento] || decision.agente_reintento}`, "aviso", "↻")
                    : ""}
                <div class="rep-muted">${escapar(decision.motivo || "")}</div>
            </div>
        `;

        return seccion(
            titulo,
            `
                <div class="rep-nota-final">
                    <span>Nota final</span>
                    <strong class="rep-nota-${tonoNota(e.nota_final)}">${e.nota_final !== null && e.nota_final !== undefined ? e.nota_final.toFixed(1) : "--"}</strong>
                    ${chip(texto, tono, icono)}
                    <span class="rep-muted">${escapar(e.comentario_general || "")}</span>
                </div>
                ${notas}
                ${cierre}
                ${recorrido(r)}
            `,
            "Califica del 1 al 10 a los 3 agentes de automatización; el sistema calcula la nota final."
        );
    }


    /* =====================================================
       INFORME (vista "Reporte completo" y PDF)
       Se lee como un informe de gerencia: membrete, resumen
       ejecutivo, cifras clave, lo que funcionó / a vigilar, plan de
       acción y detalle. El trabajo de los agentes va como anexo.
    ===================================================== */

    function fechaLarga(iso) {

        const texto = new Date(`${iso}T12:00:00`).toLocaleDateString("es-PE", {
            weekday: "long", day: "numeric", month: "long", year: "numeric"
        });

        return texto.charAt(0).toUpperCase() + texto.slice(1);
    }


    function membrete(r) {

        const [icono, texto, tono] = CALIFICACION[r.calificacion] || ["", "", "neutro"];

        const cabecera = esConsulta(r)
            ? `
                <div class="inf-tipo">Consulta a los agentes</div>
                <div class="inf-fecha">“${escapar(r.pregunta)}”</div>
                <div class="inf-meta">
                    Kimbos Delivery · Periodo analizado: ${r.desde ? `${fechaCorta(r.desde)} al ${fechaCorta(r.hasta)}` : "--"}
                </div>
            `
            : `
                <div class="inf-tipo">Informe operativo diario</div>
                <div class="inf-fecha">${fechaLarga(r.fecha)}</div>
                <div class="inf-meta">
                    Kimbos Delivery ·
                    ${r.origen === "PROGRAMADO" ? "Generado automáticamente a las 23:00" : "Generado a pedido del administrador"}
                </div>
            `;

        return `
            <header class="inf-membrete">
                <div>${cabecera}</div>
                <div class="inf-sellos">
                    ${r.calificacion ? chip(texto, tono, icono) : ""}
                    ${r.nota_final !== null && r.nota_final !== undefined
                        ? chip(`Calidad verificada ${Number(r.nota_final).toFixed(1)}/10`, tonoNota(Number(r.nota_final)), "⭐")
                        : ""}
                </div>
            </header>
        `;
    }


    /* Cinco cifras clave con su comparación */
    function cifrasClave(r) {

        const m = r.metricas || {};
        const ml = m.modelo_ml || {};
        const ayer = (m.comparacion || {}).dia_anterior || {};
        const aTiempo = m.porcentaje_retrasos === null || m.porcentaje_retrasos === undefined
            ? null
            : Math.round((100 - Number(m.porcentaje_retrasos)) * 10) / 10;

        // Periodo de varios dias: promedio diario frente al periodo anterior
        const varios = (m.dias || 1) > 1;
        const actual = (m.comparacion || {}).promedio_diario_periodo || {};
        const antes = (m.comparacion || {}).promedio_diario_periodo_anterior || {};

        const cifra = (titulo, valor, detalle) => `
            <div class="inf-cifra">
                <div class="inf-cifra-titulo">${titulo}</div>
                <div class="inf-cifra-valor">${valor}</div>
                <div class="inf-cifra-detalle">${detalle || "&nbsp;"}</div>
            </div>
        `;

        return `
            <div class="inf-cifras">
                ${cifra("Pedidos", m.pedidos ?? 0, varios
                    ? badgeComparacion(actual.pedidos, antes.pedidos, "por día vs periodo anterior", { decimales: 1 })
                    : badgeComparacion(m.pedidos, ayer.pedidos, "vs ayer", { decimales: 1 }))}
                ${cifra("Ventas", soles(m.ventas_soles), varios
                    ? badgeComparacion(actual.ventas_soles, antes.ventas_soles, "por día vs anterior", { prefijo: "S/ ", decimales: 2 })
                    : badgeComparacion(m.ventas_soles, ayer.ventas_soles, "vs ayer", { prefijo: "S/ ", decimales: 2 }))}
                ${cifra("Ticket promedio", soles(m.ticket_promedio_soles), "Gasto por pedido")}
                ${cifra("Entregas a tiempo", aTiempo === null ? "--" : `${aTiempo} %`,
                    `${m.entregas_evaluadas ?? 0} entregas · ${m.tiempo_real_promedio_min ?? "--"} min prom.`)}
                ${cifra("Acierto de la predicción", porcentaje(ml.porcentaje_acierto),
                    `${ml.aciertos ?? 0} de ${ml.predicciones_evaluadas ?? 0} pedidos`)}
            </div>
        `;
    }


    function planDeAccion(r) {

        const filas = (r.recomendaciones || []).map(normalizarRecomendacion).map((x, i) => [
            `<span class="inf-num">${i + 1}</span>`,
            `<strong>${escapar(x.titulo)}</strong><div class="rep-muted">${escapar(x.accion)}</div>`,
            escapar(RESPONSABLE[x.responsable] || x.responsable || "--"),
            escapar(x.horario || "--"),
            escapar(x.meta || "--"),
            chip(x.prioridad, PRIORIDAD[x.prioridad] || "neutro")
        ]);

        return `
            <div class="rep-refuerzo">
                🛵 Equipo sugerido${esConsulta(r) ? "" : " para mañana"}: <strong>${r.repartidores_sugeridos ?? "--"} repartidor(es)</strong>
                ${r.franja_refuerzo ? ` · reforzar de ${escapar(r.franja_refuerzo)}` : ""}
            </div>
            ${tabla(["#", "Acción", "Responsable", "Horario", "Meta", "Prioridad"], filas, "Sin acciones.")}
        `;
    }


    function hallazgosInforme(r) {

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

        return `<div class="rep-hallazgos">${hallazgos || `<p class="rep-muted">Sin hallazgos.</p>`}</div>`;
    }


    function vistaCompleta(r) {

        // Mientras se genera, o si es un reporte a medias, se muestran
        // los pasos en el orden de los agentes.
        if (r.estado !== "LISTO" || !r.titulo) {
            return `
                ${vistaRedactor(r)}
                ${vistaDatos(r)}
                ${vistaOrquestador(r)}
                ${vistaAnalista(r)}
                ${vistaEstratega(r)}
                ${vistaEvaluador(r)}
            `;
        }

        return `
            <article class="inf">

                ${membrete(r)}

                <section class="inf-resumen">
                    <div class="inf-etiqueta">${esConsulta(r) ? "Respuesta" : "Resumen ejecutivo"}</div>
                    <h2>${escapar(r.titulo)}</h2>
                    <p>${escapar(r.resumen)}</p>
                </section>

                ${cifrasClave(r)}

                ${puntosInforme(r)}

                ${r.conclusion ? `
                    <div class="inf-prioridad">
                        <div class="inf-etiqueta">${esConsulta(r) ? "Recomendación principal" : "Prioridad número uno para mañana"}</div>
                        <div>${escapar(r.conclusion)}</div>
                    </div>
                ` : ""}

                ${seccion(esConsulta(r) ? "1. Plan de acción" : "1. Plan de acción para mañana", planDeAccion(r))}

                ${seccion(esConsulta(r) ? "2. Hallazgos" : "2. Hallazgos del día", hallazgosInforme(r))}

                <div class="inf-detalle">
                    <div class="inf-separador">3. Detalle de la operación</div>
                    ${vistaDatos(r, { sinIndicadores: true })}
                </div>

                ${resumenSintetico(r) ? `
                    <div class="inf-separador">${esConsulta(r) ? "4. Resumen sintético del periodo" : "4. Resumen sintético del día"}</div>
                    <div class="inf-sintesis">${resumenSintetico(r)}</div>
                ` : ""}

                <div class="inf-anexo">
                    <div class="inf-separador">Anexo · Control de calidad del sistema multiagente</div>
                    <p class="rep-muted">
                        ${esConsulta(r) ? "Esta respuesta la prepararon" : "Este informe lo prepararon"} 5 agentes de IA: el Orquestador planificó el trabajo,
                        tres agentes de automatización lo hicieron y el Evaluador calificó su calidad.
                        Las cifras las calcula el sistema; los agentes solo las interpretan.
                    </p>
                    ${vistaOrquestador(r)}
                    ${vistaEvaluador(r)}
                </div>

            </article>
        `;
    }


    function pie(r) {

        if (esConsulta(r)) {
            return `
                <div class="rep-pie">
                    Kimbos Delivery · Consulta del ${r.creado ? new Date(r.creado).toLocaleString("es-PE") : "--"}
                    · Sistema multiagente: Orquestador → Analista de datos → Estratega → Redactor → Evaluador
                </div>
            `;
        }

        return `
            <div class="rep-pie">
                Kimbos Delivery · Reporte del ${fechaCorta(r.fecha)} ·
                ${r.origen === "PROGRAMADO" ? "Generado automáticamente (Cloud Scheduler)" : "Generado manualmente"}
                ${r.generado ? `el ${new Date(r.generado).toLocaleString("es-PE")}` : ""}
                · Sistema multiagente: Orquestador → Analista de datos → Estratega → Redactor → Evaluador
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

        const plan = (r.orquestacion || {}).plan;

        return {
            datos: `${m.pedidos ?? 0} pedidos analizados`,
            orquestador: plan
                ? (esConsulta(r) && r.desde ? `${fechaCorta(r.desde).slice(0, 5)} al ${fechaCorta(r.hasta).slice(0, 5)}` : `Prioridad ${plan.prioridad}`)
                : "—",
            analista: `${(r.hallazgos || []).length} hallazgos`,
            estratega: `${(r.recomendaciones || []).length} acciones · ${r.repartidores_sugeridos ?? "--"} repartidores`,
            redactor: r.calificacion ? (CALIFICACION[r.calificacion] || [])[1] || "Respuesta lista" : "Respuesta lista",
            evaluador: r.nota_final !== null && r.nota_final !== undefined ? `Nota final ${Number(r.nota_final).toFixed(1)}` : "—"
        }[paso.clave];
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
                    📄 ${esConsulta(r) ? "Respuesta completa" : "Reporte completo"}
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
                : modo === "consulta"
                    ? `
                        <div class="alert alert-light border">
                            Escribe una pregunta o elige un ejemplo. El Orquestador la entiende,
                            elige el periodo y reparte el trabajo entre los agentes.
                        </div>
                    `
                    : `
                        <div class="alert alert-light border">
                            Aún no hay reportes. Se generan solos cada día a las 23:00,
                            o puedes generar el de hoy con el botón.
                        </div>
                    `;
            return;
        }

        // Sin pedidos o pregunta ajena al negocio: respuesta corta
        if (r.estado === "SIN_DATOS" || r.estado === "FUERA_DE_ALCANCE") {
            contenido.innerHTML = `
                <div class="rep">
                    <div class="rep-resumen">
                        ${esConsulta(r) ? `<div class="inf-tipo">Consulta: “${escapar(r.pregunta)}”</div>` : ""}
                        <h2>${escapar(r.titulo)}</h2>
                        <p class="mb-0">
                            ${escapar(r.resumen)}
                            ${esConsulta(r)
                                ? (r.estado === "FUERA_DE_ALCANCE"
                                    ? " Solo trabajó el Orquestador; los demás agentes no se ejecutaron."
                                    : " Los agentes de análisis no se ejecutaron.")
                                : " Los agentes no se ejecutaron (costo 0)."}
                        </p>
                    </div>
                    ${pie(r)}
                </div>
            `;
            return;
        }

        const VISTAS = {
            datos: vistaDatos,
            orquestador: vistaOrquestador,
            analista: vistaAnalista,
            estratega: vistaEstratega,
            redactor: vistaRedactor,
            evaluador: vistaEvaluador
        };

        const cuerpo = vista === "completo"
            ? vistaCompleta(r)
            : VISTAS[PASOS[vista].clave](r);

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

        const url = modo === "consulta"
            ? `/api/automatizacion/consultas/${reporteActual.id}/pasos/${paso.clave}`
            : `/api/automatizacion/reportes/pasos/${paso.clave}`;

        const respuesta = await fetch(url, {
            method: "POST",
            headers: cabeceras(),
            body: JSON.stringify(fecha && modo === "reporte" ? { fecha } : {})
        });

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo completar el paso.");
        }

        return modo === "consulta" ? datos.consulta : datos.reporte;
    }


    /* Consulta nueva: se registra la pregunta y trabajan los 6 pasos. */
    async function preguntar(pregunta) {

        botonPreguntar.disabled = true;

        try {

            const respuesta = await fetch("/api/automatizacion/consultas", {
                method: "POST",
                headers: cabeceras(),
                body: JSON.stringify({ pregunta })
            });

            const datos = await respuesta.json();

            if (!respuesta.ok || !datos.ok) {
                throw new Error(datos.mensaje || "No se pudo registrar la pregunta.");
            }

            reporteActual = datos.consulta;
            campoPregunta.value = "";

        } catch (error) {
            botonPreguntar.disabled = false;
            alert(error.message);
            return;
        }

        await generarSecuencial(0);
    }


    /* Ejecuta los pasos en orden, uno por uno, desde "desde". */
    async function generarSecuencial(desde = 0) {

        botonGenerar.disabled = true;
        botonPreguntar.disabled = true;
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

                // Sin pedidos o pregunta ajena al negocio: termina aqui
                if (reporteActual.estado === "SIN_DATOS" || reporteActual.estado === "FUERA_DE_ALCANCE") {
                    break;
                }
            }

            generacion = null;
            vista = "completo";
            pintar();

            await cargarLista(modo === "consulta" ? reporteActual.id : fecha);

        } catch (error) {

            generacion = { ...generacion, estado: "error", mensaje: error.message };
            pintar();

        } finally {
            botonGenerar.disabled = false;
            botonPreguntar.disabled = false;
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
                    .rep-kpi, .rep-hallazgo, .rep-tabla tr, .rep-resumen, .rep-conclusion,
                    .inf-cifra, .inf-punto, .inf-prioridad, .inf-membrete { break-inside: avoid; }
                    .inf-separador { break-after: avoid; }
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
                    <span>${esConsulta(reporteActual) ? "Consulta a los agentes de IA" : `Reporte diario del sistema multiagente · ${fechaCorta(reporteActual.fecha)}`}</span>
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

        const etiqueta = (r) => esConsulta(r)
            ? `${new Date(r.creado).toLocaleDateString("es-PE", { day: "2-digit", month: "2-digit" })} · ${r.pregunta.length > 45 ? `${r.pregunta.slice(0, 45)}…` : r.pregunta}`
            : fechaCorta(r.fecha);

        selector.innerHTML = reportes.length
            ? reportes.map((r, i) => `<option value="${i}">${escapar(etiqueta(r))}</option>`).join("")
            : `<option>${modo === "consulta" ? "Sin consultas anteriores" : "Sin reportes"}</option>`;

        selector.disabled = !reportes.length;
    }


    /* Historial del modo: consultas (por id) o reportes (por fecha). */
    async function cargarLista(elegido = null) {

        const consulta = modo === "consulta";

        const respuesta = await fetch(
            consulta ? "/api/automatizacion/consultas" : "/api/automatizacion/reportes",
            { headers: cabeceras() }
        );
        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo cargar el historial.");
        }

        reportes = consulta ? datos.consultas : datos.reportes;
        llenarSelector();

        const indice = Math.max(0, reportes.findIndex((r) => (consulta ? r.id : r.fecha) === elegido));
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

    formConsulta.addEventListener("submit", (evento) => {
        evento.preventDefault();
        const pregunta = campoPregunta.value.trim();
        if (pregunta && !generacion) {
            preguntar(pregunta);
        }
    });

    formConsulta.addEventListener("click", (evento) => {
        const ejemplo = evento.target.closest("[data-ejemplo]");
        if (ejemplo) {
            campoPregunta.value = ejemplo.dataset.ejemplo;
            campoPregunta.focus();
        }
    });

    /* Cambio de modo: consulta o reporte diario */
    modal.addEventListener("click", (evento) => {

        const boton = evento.target.closest("[data-modo]");

        if (!boton || boton.dataset.modo === modo || (generacion && generacion.estado === "trabajando")) {
            return;
        }

        modo = boton.dataset.modo;
        PASOS = modo === "consulta" ? PASOS_CONSULTA : PASOS_REPORTE;
        reporteActual = null;
        reportes = [];

        modal.querySelectorAll("[data-modo]").forEach((b) => {
            b.classList.toggle("activo", b.dataset.modo === modo);
            b.setAttribute("aria-selected", b.dataset.modo === modo ? "true" : "false");
        });

        formConsulta.classList.toggle("d-none", modo !== "consulta");
        botonGenerar.classList.toggle("d-none", modo !== "reporte");
        subtitulo.textContent = modo === "consulta"
            ? "Pregunta lo que necesites: trabajan 5 agentes (Orquestador → Analista → Estratega → Redactor → Evaluador)."
            : "Generado cada día a las 23:00 por 5 agentes: Orquestador → Analista de datos → Estratega → Redactor → Evaluador.";

        cargar();
    });


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
        .rep-pasos { flex: 1 1 100%; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 6px; min-width: 0; }
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
        .rep-paso-flecha { display: none; }
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

        /* Informe de gerencia */
        .inf-fecha q { quotes: none; }
        .inf { color: #1d1d1b; }
        .inf-membrete { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: flex-start;
                        padding-bottom: 14px; margin-bottom: 18px; border-bottom: 2px solid #1d1d1b; }
        .inf-tipo { font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #ff6b00; }
        .inf-fecha { font-size: 22px; font-weight: 800; letter-spacing: -.01em; }
        .inf-meta { font-size: 12px; color: #52514e; }
        .inf-sellos { display: flex; flex-wrap: wrap; gap: 6px; }
        .inf-etiqueta { font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #52514e; margin-bottom: 4px; }
        .inf-resumen h2 { font-size: 21px; margin: 0 0 6px; }
        .inf-resumen p { font-size: 15px; line-height: 1.6; margin: 0; max-width: 75ch; }
        .inf-cifras { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 18px 0; }
        .inf-cifra { border: 1px solid #ecebe6; border-radius: 12px; padding: 10px 12px; background: #fff; }
        .inf-cifra-titulo { font-size: 11.5px; color: #52514e; font-weight: 600; }
        .inf-cifra-valor { font-size: 22px; font-weight: 800; font-variant-numeric: tabular-nums; line-height: 1.25; }
        .inf-cifra-detalle { font-size: 11px; color: #898781; margin-top: 2px; }
        .inf-puntos { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 14px 0; }
        .inf-punto { border-radius: 12px; padding: 12px 14px; border: 1px solid; }
        .inf-punto ul { margin: 0; padding-left: 18px; }
        .inf-punto li { margin: 3px 0; }
        .inf-punto-titulo { font-weight: 700; margin-bottom: 4px; }
        .inf-punto-ok { background: #f3faf3; border-color: #cfe9cf; }
        .inf-punto-ok .inf-punto-titulo { color: #1d5e1d; }
        .inf-punto-aviso { background: #fffaeb; border-color: #f3d98f; }
        .inf-punto-aviso .inf-punto-titulo { color: #6b4d00; }
        .inf-prioridad { margin: 14px 0 4px; padding: 12px 16px; border-left: 4px solid #ff6b00; background: #fff8f2;
                         border-radius: 8px; font-size: 15px; font-weight: 600; }
        .inf-num { display: inline-flex; width: 22px; height: 22px; border-radius: 50%; align-items: center; justify-content: center;
                   background: #1d1d1b; color: #fff; font-size: 11px; font-weight: 700; }
        .inf-separador { margin-top: 26px; padding-top: 10px; border-top: 1px solid #e1e0d9; font-size: 15px; font-weight: 700; }
        .inf-detalle .rep-seccion:first-child, .inf-anexo .rep-seccion:first-of-type { margin-top: 12px; }
        .inf-anexo { margin-top: 10px; }
        .inf-sintesis { margin-top: 12px; }
        .inf-res-valor { font-size: 16px; font-weight: 800; font-variant-numeric: tabular-nums; }

        /* Orquestador y Evaluador */
        .rep-seccion h3 .rep-chip { vertical-align: middle; margin-left: 4px; }
        .rep-encargo { font-size: 12px; color: #4b43a8; margin: -2px 0 8px; }
        .rep-orq { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 10px; align-items: center;
                   padding: 12px 14px; border-radius: 14px; background: #f1efff; border: 1px solid #d8d4f5; margin-bottom: 8px; }
        .rep-orq-enfoque { font-size: 17px; font-weight: 700; }
        .rep-nota-final { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px;
                          padding: 12px 14px; border-radius: 14px; background: #fffaf0; border: 1px solid #f3d98f; }
        .rep-nota-final strong { font-size: 26px; font-weight: 800; }
        .rep-nota-ok { color: #1d5e1d; }
        .rep-nota-aviso { color: #6b4d00; }
        .rep-nota-mal { color: #8a1f1f; }
        .rep-decision { margin-top: 10px; padding: 10px 14px; border-radius: 12px; background: #f1efff; border: 1px solid #d8d4f5; }
        .rep-flujo { display: flex; flex-wrap: wrap; gap: 4px 6px; align-items: center; margin-top: 10px; padding: 6px 10px;
                     border-radius: 10px; border: 1px dashed #d8d4f5; background: #fff; font-size: 11.5px; }
        .rep-flujo small { color: #52514e; }
        .rep-flujo b { color: #9b93e6; font-weight: 400; }

        @media (max-width: 1100px) {
            .rep-pasos { grid-template-columns: repeat(3, minmax(0, 1fr)); }
        }

        @media (max-width: 860px) {
            .inf-cifras { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .inf-puntos { grid-template-columns: 1fr; }
            .rep-pasos { grid-template-columns: 1fr; }
            .rep-kpis { grid-template-columns: repeat(2, 1fr); }
            .rep-dos { grid-template-columns: 1fr; }
        }
    `;

    const estilo = document.createElement("style");
    estilo.textContent = ESTILOS;
    document.head.appendChild(estilo);

})();

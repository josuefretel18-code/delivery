/* ========================================================
   REPORTE DIARIO (sistema multiagente)
   Datos del día (SQL) -> Analista de datos -> Estratega -> Redactor
   La misma vista se usa en pantalla y para exportar a PDF.
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

    let reportes = [];
    let reporteActual = null;


    /* Estilos del reporte: los mismos en pantalla y en el PDF. */
    const ESTILOS = `
        .rep { color: #0b0b0b; font-size: 14px; line-height: 1.45; }
        .rep h2 { font-size: 20px; font-weight: 700; margin: 0 0 6px; }
        .rep h3 { font-size: 15px; font-weight: 700; margin: 22px 0 10px; }
        .rep-muted { color: #52514e; font-size: 12px; }

        .rep-flujo { display: flex; align-items: stretch; gap: 6px; margin-bottom: 18px; }
        .rep-paso { flex: 1; border: 1px solid #e1e0d9; border-radius: 12px; padding: 10px 12px; background: #fff; }
        .rep-paso-cab { display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 13px; }
        .rep-paso-num { width: 24px; height: 24px; border-radius: 50%; background: #171717; color: #fff;
                        display: inline-flex; align-items: center; justify-content: center; font-size: 12px; flex: none; }
        .rep-paso-sal { color: #52514e; font-size: 12px; margin-top: 4px; }
        .rep-flecha { display: flex; align-items: center; color: #898781; font-size: 18px; }

        .rep-resumen { border-radius: 14px; padding: 16px 18px; background: #f5f3ff; border: 1px solid #d8d4f5; }
        .rep-etiqueta { font-size: 12px; font-weight: 700; color: #5b4fc7; margin-bottom: 4px; }
        .rep-calif { display: inline-flex; align-items: center; gap: 6px; border-radius: 999px; padding: 3px 10px;
                     font-size: 12px; font-weight: 700; border: 1px solid; }
        .rep-calif-BUENO { background: #e9f7e9; border-color: #0ca30c; color: #0b0b0b; }
        .rep-calif-REGULAR { background: #fff6dd; border-color: #fab219; color: #0b0b0b; }
        .rep-calif-CRITICO { background: #fdeaea; border-color: #d03b3b; color: #0b0b0b; }

        .rep-kpis { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
        .rep-kpi { border: 1px solid #e1e0d9; border-radius: 12px; padding: 10px 12px; background: #fff; }
        .rep-kpi-t { font-size: 12px; color: #52514e; }
        .rep-kpi-v { font-size: 20px; font-weight: 700; }
        .rep-kpi-c { font-size: 11px; color: #898781; }

        .rep-hallazgo { display: flex; gap: 10px; padding: 9px 0; border-bottom: 1px solid #eeede8; }
        .rep-hallazgo:last-child { border-bottom: 0; }
        .rep-hallazgo-ic { font-size: 16px; line-height: 1.2; }
        .rep-tipo { font-size: 10px; font-weight: 700; letter-spacing: .03em; color: #52514e; }

        .rep-tabla { width: 100%; border-collapse: collapse; font-size: 12.5px; }
        .rep-tabla th { text-align: left; font-weight: 700; color: #52514e; border-bottom: 1px solid #c3c2b7; padding: 6px 8px; }
        .rep-tabla td { border-bottom: 1px solid #eeede8; padding: 7px 8px; vertical-align: top; }
        .rep-num { font-variant-numeric: tabular-nums; }
        .rep-prio { display: inline-block; border-radius: 6px; padding: 1px 7px; font-size: 11px; font-weight: 700; border: 1px solid; }
        .rep-prio-ALTA { border-color: #d03b3b; color: #a32626; }
        .rep-prio-MEDIA { border-color: #fab219; color: #7a5300; }
        .rep-prio-BAJA { border-color: #c3c2b7; color: #52514e; }

        .rep-dos { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
        .rep-barra { display: flex; align-items: center; gap: 8px; font-size: 12px; margin: 3px 0; }
        .rep-barra-h { width: 34px; color: #52514e; font-variant-numeric: tabular-nums; }
        .rep-barra-f { height: 12px; border-radius: 0 4px 4px 0; background: #2a78d6; min-width: 2px; }

        .rep-conclusion { border-left: 4px solid #2a78d6; background: #f4f8fd; border-radius: 8px; padding: 12px 14px; }
        .rep-pie { margin-top: 22px; padding-top: 10px; border-top: 1px solid #e1e0d9; font-size: 11px; color: #898781; }

        @media (max-width: 760px) {
            .rep-flujo { flex-direction: column; }
            .rep-flecha { justify-content: center; transform: rotate(90deg); }
            .rep-kpis { grid-template-columns: repeat(2, 1fr); }
            .rep-dos { grid-template-columns: 1fr; }
        }
    `;

    const CALIFICACION = {
        BUENO: "✅ Día bueno",
        REGULAR: "⚠️ Día regular",
        CRITICO: "⛔ Día crítico"
    };

    const TIPO_HALLAZGO = {
        POSITIVO: ["✅", "Positivo"],
        ALERTA: ["⚠️", "Alerta"],
        NEUTRO: ["ℹ️", "Neutro"]
    };

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


    /* Diferencia con un valor de comparación: "+3 vs ayer". */
    function diferencia(actual, referencia, sufijo, decimales = 0, prefijo = "") {

        if (referencia === null || referencia === undefined || actual === null || actual === undefined) {
            return "";
        }

        const cambio = Number(actual) - Number(referencia);
        const signo = cambio > 0 ? "+" : cambio < 0 ? "−" : "±";

        // Sin ceros innecesarios: 4.0 -> 4 (pero S/ siempre con 2 decimales)
        const valor = prefijo
            ? Math.abs(cambio).toFixed(decimales)
            : String(Number(Math.abs(cambio).toFixed(decimales)));

        return `${signo}${prefijo}${valor} ${sufijo}`;
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


    function construirHTML(reporte) {

        const m = reporte.metricas || {};
        const ml = m.modelo_ml || {};
        const comp = m.comparacion || {};
        const ayer = comp.dia_anterior || {};
        const semana = comp.promedio_diario_7_dias_previos || {};

        const hallazgos = (reporte.hallazgos || []).map(normalizarHallazgo);
        const recomendaciones = (reporte.recomendaciones || []).map(normalizarRecomendacion);

        // ---------- Flujo de agentes ----------
        const flujo = `
            <div class="rep-flujo">
                <div class="rep-paso">
                    <div class="rep-paso-cab"><span class="rep-paso-num">0</span>📊 Datos del día</div>
                    <div class="rep-paso-sal">El sistema calcula las cifras con SQL: ${m.pedidos ?? 0} pedidos.</div>
                </div>
                <div class="rep-flecha">→</div>
                <div class="rep-paso">
                    <div class="rep-paso-cab"><span class="rep-paso-num">1</span>🔍 Analista de datos</div>
                    <div class="rep-paso-sal">${hallazgos.length} hallazgos con comparaciones.</div>
                </div>
                <div class="rep-flecha">→</div>
                <div class="rep-paso">
                    <div class="rep-paso-cab"><span class="rep-paso-num">2</span>🧭 Estratega</div>
                    <div class="rep-paso-sal">${recomendaciones.length} recomendaciones y ${reporte.repartidores_sugeridos ?? "--"} repartidores para mañana.</div>
                </div>
                <div class="rep-flecha">→</div>
                <div class="rep-paso">
                    <div class="rep-paso-cab"><span class="rep-paso-num">3</span>✍️ Redactor</div>
                    <div class="rep-paso-sal">Resumen ejecutivo, calificación y conclusión.</div>
                </div>
            </div>
        `;

        // ---------- Resumen ejecutivo ----------
        const resumen = `
            <div class="rep-resumen">
                <div class="d-flex" style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
                    <div class="rep-etiqueta">3 · Agente Redactor: resumen ejecutivo</div>
                    ${reporte.calificacion
                        ? `<span class="rep-calif rep-calif-${reporte.calificacion}">${CALIFICACION[reporte.calificacion]}</span>`
                        : ""}
                </div>
                <h2>${escapar(reporte.titulo)}</h2>
                <div>${escapar(reporte.resumen)}</div>
            </div>
        `;

        // ---------- Indicadores ----------
        const kpi = (titulo, valor, comparacion) => `
            <div class="rep-kpi">
                <div class="rep-kpi-t">${titulo}</div>
                <div class="rep-kpi-v">${valor}</div>
                <div class="rep-kpi-c">${comparacion || "&nbsp;"}</div>
            </div>
        `;

        const comparar = (actual, campo, prefijo = "", decimales = 0) => [
            diferencia(actual, ayer[campo], "vs ayer", decimales, prefijo),
            diferencia(actual, semana[campo], "vs prom. 7 días", decimales, prefijo)
        ].filter(Boolean).join(" · ");

        const indicadores = `
            <h3>Indicadores del día</h3>
            <div class="rep-kpis">
                ${kpi("Pedidos", m.pedidos ?? 0, comparar(m.pedidos, "pedidos", "", 1))}
                ${kpi("Ventas", soles(m.ventas_soles), comparar(m.ventas_soles, "ventas_soles", "S/ ", 2))}
                ${kpi("Ticket promedio", soles(m.ticket_promedio_soles), `${m.entregados ?? 0} entregados · ${m.cancelados ?? 0} cancelados`)}
                ${kpi("Retrasos reales", porcentaje(m.porcentaje_retrasos),
                    `${m.entregas_con_retraso ?? 0} de ${m.entregas_evaluadas ?? 0} entregas · prometido ${m.tiempo_estimado_promedio_min ?? "--"} min, real ${m.tiempo_real_promedio_min ?? "--"} min`)}
                ${kpi("Acierto del modelo ML", porcentaje(ml.porcentaje_acierto),
                    `${ml.aciertos ?? 0} de ${ml.predicciones_evaluadas ?? 0} predicciones · riesgo prom. ${ml.riesgo_promedio_pct ?? "--"} %`)}
                ${kpi("Repartidores para mañana", reporte.repartidores_sugeridos ?? "--",
                    `hoy en turno: ${m.repartidores_disponibles ?? "--"}${reporte.franja_refuerzo ? ` · refuerzo ${escapar(reporte.franja_refuerzo)}` : ""}`)}
            </div>
        `;

        // ---------- Hallazgos ----------
        const listaHallazgos = hallazgos.map((h) => {
            const [icono, etiqueta] = TIPO_HALLAZGO[h.tipo] || TIPO_HALLAZGO.NEUTRO;
            return `
                <div class="rep-hallazgo">
                    <div class="rep-hallazgo-ic">${icono}</div>
                    <div>
                        <div class="rep-tipo">${etiqueta.toUpperCase()}</div>
                        ${h.titulo ? `<strong>${escapar(h.titulo)}</strong><br>` : ""}
                        <span>${escapar(h.detalle)}</span>
                    </div>
                </div>
            `;
        }).join("");

        // ---------- Recomendaciones ----------
        const tablaRecomendaciones = recomendaciones.length
            ? `
                <table class="rep-tabla">
                    <thead>
                        <tr><th>Prioridad</th><th>Acción</th><th>Responsable</th><th>Horario</th><th>Meta</th></tr>
                    </thead>
                    <tbody>
                        ${recomendaciones.map((r) => `
                            <tr>
                                <td><span class="rep-prio rep-prio-${escapar(r.prioridad)}">${escapar(r.prioridad)}</span></td>
                                <td><strong>${escapar(r.titulo)}</strong><br>${escapar(r.accion)}</td>
                                <td>${escapar(RESPONSABLE[r.responsable] || r.responsable || "--")}</td>
                                <td>${escapar(r.horario || "--")}</td>
                                <td>${escapar(r.meta || "--")}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            `
            : `<p class="rep-muted">Sin recomendaciones.</p>`;

        // ---------- Operación del día ----------
        const horas = Object.entries(m.pedidos_por_hora || {});
        const maxHora = Math.max(1, ...horas.map(([, n]) => n));

        const barrasHora = horas.length
            ? horas.map(([hora, n]) => `
                <div class="rep-barra">
                    <span class="rep-barra-h">${escapar(hora)}</span>
                    <span class="rep-barra-f" style="width:${Math.round((n / maxHora) * 70)}%"></span>
                    <span class="rep-num">${n}</span>
                </div>
            `).join("")
            : `<p class="rep-muted">Sin pedidos.</p>`;

        const tablaProductos = (m.productos_mas_vendidos || []).length
            ? `
                <table class="rep-tabla">
                    <thead><tr><th>Producto</th><th>Unidades</th></tr></thead>
                    <tbody>
                        ${m.productos_mas_vendidos.map((p) => `
                            <tr><td>${escapar(p.producto)}</td><td class="rep-num">${p.unidades}</td></tr>
                        `).join("")}
                    </tbody>
                </table>
            `
            : `<p class="rep-muted">Sin ventas.</p>`;

        const tablaRepartidores = (m.entregas_por_repartidor || []).length
            ? `
                <table class="rep-tabla">
                    <thead><tr><th>Repartidor</th><th>Entregas</th><th>Retrasos</th><th>Tiempo real prom.</th></tr></thead>
                    <tbody>
                        ${m.entregas_por_repartidor.map((r) => `
                            <tr>
                                <td>${escapar(r.repartidor)}</td>
                                <td class="rep-num">${r.entregas}</td>
                                <td class="rep-num">${r.retrasos}</td>
                                <td class="rep-num">${r.tiempo_real_promedio_min ?? "--"} min</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            `
            : `<p class="rep-muted">Sin pedidos asignados a repartidores.</p>`;

        const tablaAlertas = (m.alertas_detalle || []).length
            ? `
                <table class="rep-tabla">
                    <thead><tr><th>Pedido</th><th>Riesgo</th><th>Acción recomendada</th><th>Min. extra</th></tr></thead>
                    <tbody>
                        ${m.alertas_detalle.map((a) => `
                            <tr>
                                <td>${escapar(a.pedido)}</td>
                                <td>${escapar(a.nivel)}</td>
                                <td>${escapar(ACCIONES[a.accion] || a.accion)}</td>
                                <td class="rep-num">${a.minutos_extra ?? 0}</td>
                            </tr>
                        `).join("")}
                    </tbody>
                </table>
            `
            : `<p class="rep-muted">Los agentes no analizaron pedidos este día.</p>`;

        // ---------- Conclusión ----------
        const conclusion = reporte.conclusion
            ? `
                <h3>Conclusión y foco para mañana</h3>
                <div class="rep-conclusion">${escapar(reporte.conclusion)}</div>
            `
            : "";

        return `
            <div class="rep">
                ${flujo}
                ${resumen}
                ${indicadores}

                <h3>1 · Agente Analista de datos: hallazgos</h3>
                ${listaHallazgos || `<p class="rep-muted">Sin hallazgos.</p>`}

                <h3>2 · Agente Estratega: plan para mañana</h3>
                ${tablaRecomendaciones}

                <h3>Operación del día</h3>
                <div class="rep-dos">
                    <div>
                        <div class="rep-etiqueta" style="color:#52514e">Pedidos por hora${m.hora_pico ? ` · pico: ${escapar(m.hora_pico)}` : ""}</div>
                        ${barrasHora}
                    </div>
                    <div>
                        <div class="rep-etiqueta" style="color:#52514e">Productos más vendidos</div>
                        ${tablaProductos}
                    </div>
                </div>

                <h3>Repartidores</h3>
                ${tablaRepartidores}

                <h3>Pedidos analizados por los agentes (alertas de riesgo)</h3>
                ${tablaAlertas}

                ${conclusion}

                <div class="rep-pie">
                    Kimbos Delivery · Reporte del ${fechaCorta(reporte.fecha)} ·
                    ${reporte.origen === "PROGRAMADO" ? "Generado automáticamente (Cloud Scheduler)" : "Generado manualmente"}
                    ${reporte.generado ? `el ${new Date(reporte.generado).toLocaleString("es-PE")}` : ""}
                    · Sistema multiagente: Analista de datos → Estratega → Redactor
                </div>
            </div>
        `;
    }


    function pintar(reporte) {

        reporteActual = reporte;
        botonPdf.disabled = !reporte || reporte.estado === "ERROR" || reporte.estado === "PROCESANDO";

        if (!reporte) {
            contenido.innerHTML = `
                <div class="alert alert-light border">
                    Aún no hay reportes. Se generan solos cada día a las 23:00,
                    o puedes generar el de hoy con el botón.
                </div>
            `;
            return;
        }

        if (reporte.estado === "ERROR") {
            contenido.innerHTML = `
                <div class="alert alert-danger">
                    No se pudo generar el reporte del ${fechaCorta(reporte.fecha)}:
                    ${escapar(reporte.error)}
                </div>
            `;
            return;
        }

        contenido.innerHTML = construirHTML(reporte);
    }


    /* Abre una ventana con el reporte listo para "Guardar como PDF". */
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
                    .rep-paso, .rep-kpi, .rep-hallazgo, .rep-tabla tr, .rep-resumen, .rep-conclusion { break-inside: avoid; }
                    h3 { break-after: avoid; }
                    * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
                    ${ESTILOS}
                    .rep-flujo { flex-direction: row !important; }
                    .rep-flecha { transform: none !important; }
                    .rep-kpis { grid-template-columns: repeat(3, 1fr) !important; }
                    .rep-dos { grid-template-columns: 1fr 1fr !important; }
                </style>
            </head>
            <body>
                <div class="marca">
                    <strong>KIMBOS</strong>
                    <span>Reporte diario del sistema multiagente · ${fechaCorta(reporteActual.fecha)}</span>
                </div>
                ${construirHTML(reporteActual)}
                <script>
                    window.onload = function () {
                        setTimeout(function () { window.print(); }, 300);
                    };
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


    async function cargar() {

        contenido.innerHTML = `<p class="text-secondary">Cargando...</p>`;

        try {

            const respuesta = await fetch("/api/automatizacion/reportes", { headers: cabeceras() });
            const datos = await respuesta.json();

            if (!respuesta.ok || !datos.ok) {
                throw new Error(datos.mensaje || "No se pudieron cargar los reportes.");
            }

            reportes = datos.reportes;
            llenarSelector();
            pintar(reportes[0]);

        } catch (error) {
            contenido.innerHTML = `<div class="alert alert-danger">${escapar(error.message)}</div>`;
        }
    }


    async function generar() {

        botonGenerar.disabled = true;
        botonGenerar.textContent = "🤖 Los agentes están trabajando (≈45 s)…";

        try {

            const respuesta = await fetch("/api/automatizacion/reportes/generar", {
                method: "POST",
                headers: cabeceras(),
                body: "{}"
            });

            const datos = await respuesta.json();

            if (!respuesta.ok || !datos.ok) {
                throw new Error(datos.mensaje || "No se pudo generar el reporte.");
            }

            await cargar();

        } catch (error) {
            alert(error.message);
        } finally {
            botonGenerar.disabled = false;
            botonGenerar.textContent = "🤖 Generar reporte de hoy";
        }
    }


    // Estilos del reporte en la página (una sola vez)
    const estilo = document.createElement("style");
    estilo.textContent = ESTILOS;
    document.head.appendChild(estilo);

    selector.addEventListener("change", () => pintar(reportes[Number(selector.value)]));
    botonGenerar.addEventListener("click", generar);
    botonPdf.addEventListener("click", exportarPdf);
    modal.addEventListener("show.bs.modal", cargar);

})();

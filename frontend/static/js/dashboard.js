/* ========================================================
   DASHBOARD DEL ADMINISTRADOR (solo lectura)
   Indicadores y gráficos del período: hoy, 7 o 30 días.

   Pensado para leerse rápido: una frase de resumen arriba,
   tres bloques (Ventas · Entregas · Inteligencia) y cada
   gráfico con su conclusión en una línea.
======================================================== */

(function () {

    const modal = document.getElementById("modalDashboard");
    const contenido = document.getElementById("contenidoDashboard");
    const filtros = document.getElementById("filtrosDashboard");

    if (!modal || !contenido) {
        return;
    }

    // Paleta validada (azul / naranja) y tinta del gráfico
    const COLOR = {
        serie1: "#2a78d6",
        serie2: "#eb6834",
        texto: "#52514e",
        apagado: "#898781",
        grilla: "#e1e0d9",
        superficie: "#ffffff",
        subeBien: "#006300",
        bajaMal: "#d03b3b"
    };

    const NOMBRE_PERIODO = {
        1: "hoy",
        7: "los últimos 7 días",
        30: "los últimos 30 días"
    };

    let periodo = 7;
    let graficos = [];


    /* Valor encima de cada barra (solo si hay pocas barras). */
    const valoresEnBarras = {
        id: "valoresEnBarras",
        afterDatasetsDraw(grafico, argumentos, opciones) {

            if (!opciones || !opciones.mostrar) {
                return;
            }

            const { ctx } = grafico;
            const horizontal = grafico.options.indexAxis === "y";
            const ultimo = grafico.data.datasets.length - 1;

            ctx.save();
            ctx.fillStyle = COLOR.texto;
            ctx.font = "600 11px system-ui, -apple-system, 'Segoe UI', sans-serif";

            grafico.getDatasetMeta(ultimo).data.forEach((barra, indice) => {

                // En barras apiladas se muestra el total arriba
                const total = grafico.data.datasets.reduce(
                    (suma, serie) => suma + (Number(serie.data[indice]) || 0), 0
                );

                if (!total) {
                    return;
                }

                const texto = opciones.formato ? opciones.formato(total) : String(total);

                if (horizontal) {
                    ctx.textAlign = "left";
                    ctx.textBaseline = "middle";
                    ctx.fillText(texto, barra.x + 6, barra.y);
                } else {
                    ctx.textAlign = "center";
                    ctx.textBaseline = "bottom";
                    ctx.fillText(texto, barra.x, barra.y - 4);
                }
            });

            ctx.restore();
        }
    };


    function escapar(valor) {

        return String(valor ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }


    function soles(valor, decimales = 2) {
        return valor === null || valor === undefined ? "--" : `S/ ${Number(valor).toFixed(decimales)}`;
    }


    function fechaCorta(iso) {
        const [, mes, dia] = iso.split("-");
        return `${dia}/${mes}`;
    }


    function hora(h) {
        return `${String(h).padStart(2, "0")}h`;
    }


    /* Comparación con el período anterior, en palabras simples. */
    function comparacion(actual, anterior, formato, mejorSiSube = true) {

        if (actual === null || actual === undefined) {
            return `<span class="dash-delta">&nbsp;</span>`;
        }

        if (anterior === null || anterior === undefined || anterior === 0) {
            return `<span class="dash-delta">Período anterior: ${anterior === 0 ? formato(0) : "--"}</span>`;
        }

        const cambio = ((actual - anterior) / anterior) * 100;

        if (Math.abs(cambio) < 0.5) {
            return `<span class="dash-delta">= igual que antes (${formato(anterior)})</span>`;
        }

        const sube = cambio > 0;
        const bueno = sube === mejorSiSube;

        return `
            <span class="dash-delta" style="color: ${bueno ? COLOR.subeBien : COLOR.bajaMal}">
                ${sube ? "▲" : "▼"} ${Math.abs(cambio).toFixed(0)} %
            </span>
            <span class="dash-delta">vs antes (${formato(anterior)})</span>
        `;
    }


    function tarjeta(icono, titulo, valor, detalle) {

        return `
            <div class="col-6 col-lg-4 col-xl-2">
                <div class="dash-tarjeta">
                    <div class="dash-tarjeta-titulo">${icono} ${titulo}</div>
                    <div class="dash-tarjeta-valor">${valor}</div>
                    <div>${detalle}</div>
                </div>
            </div>
        `;
    }


    function bloque(icono, titulo, descripcion, cuerpo) {

        return `
            <section class="dash-bloque">
                <div class="dash-bloque-cab">
                    <h5>${icono} ${titulo}</h5>
                    <p>${descripcion}</p>
                </div>
                <div class="row g-3">${cuerpo}</div>
            </section>
        `;
    }


    /* Panel con título, conclusión en una línea y contenido. */
    function panel(titulo, conclusion, cuerpo, columnas = "col-lg-6") {

        return `
            <div class="col-12 ${columnas}">
                <div class="dash-panel">
                    <h6 class="dash-panel-titulo">${titulo}</h6>
                    ${conclusion ? `<div class="dash-conclusion">${conclusion}</div>` : ""}
                    ${cuerpo}
                </div>
            </div>
        `;
    }


    function lienzo(id, etiqueta, alto = 230) {

        return `
            <div style="position: relative; height: ${alto}px">
                <canvas id="${id}" role="img" aria-label="${escapar(etiqueta)}"></canvas>
            </div>
        `;
    }


    function vacio(texto = "Sin datos en este período.") {
        return `<p class="text-secondary small mb-0">${texto}</p>`;
    }


    /* Opciones comunes: marcas finas, grilla tenue, un solo eje. */
    function opcionesBase({ apiladas = false, horizontal = false, valores = false, formato = null } = {}) {

        const ejeValor = {
            beginAtZero: true,
            stacked: apiladas,
            grace: "12%",
            grid: { color: COLOR.grilla },
            border: { display: false },
            ticks: { color: COLOR.apagado, font: { size: 11 }, precision: 0 }
        };

        const ejeCategoria = {
            stacked: apiladas,
            grid: { display: false },
            border: { color: "#c3c2b7" },
            ticks: {
                color: horizontal ? COLOR.texto : COLOR.apagado,
                font: { size: horizontal ? 12 : 11 },
                maxRotation: 0,
                autoSkip: true
            }
        };

        return {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: horizontal ? "y" : "x",
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { display: false },
                valoresEnBarras: { mostrar: valores, formato },
                tooltip: {
                    backgroundColor: "#0b0b0b",
                    titleColor: "#ffffff",
                    bodyColor: "#ffffff",
                    padding: 10,
                    cornerRadius: 8
                }
            },
            scales: horizontal
                ? { x: ejeValor, y: ejeCategoria }
                : { x: ejeCategoria, y: ejeValor }
        };
    }


    function barras(color) {

        return {
            backgroundColor: color,
            borderColor: COLOR.superficie,
            borderWidth: 2,
            borderSkipped: "start",
            borderRadius: 4,
            maxBarThickness: 34
        };
    }


    function crearGrafico(id, configuracion) {

        const elemento = document.getElementById(id);

        if (elemento && window.Chart) {
            configuracion.plugins = [valoresEnBarras];
            graficos.push(new Chart(elemento, configuracion));
        }
    }


    /* 30 días: se agrupa por semanas para no mostrar 30 barras casi vacías. */
    function agruparPorSemana(dias) {

        const semanas = [];

        for (let fin = dias.length; fin > 0; fin -= 7) {

            const tramo = dias.slice(Math.max(fin - 7, 0), fin);

            semanas.unshift({
                etiqueta: `${fechaCorta(tramo[0].dia)}–${fechaCorta(tramo[tramo.length - 1].dia)}`,
                pedidos: tramo.reduce((s, d) => s + d.pedidos, 0),
                ventas_soles: tramo.reduce((s, d) => s + d.ventas_soles, 0),
                a_tiempo: tramo.reduce((s, d) => s + d.a_tiempo, 0),
                retrasados: tramo.reduce((s, d) => s + d.retrasados, 0)
            });
        }

        return semanas;
    }


    function pintar(datos) {

        graficos.forEach((g) => g.destroy());
        graficos = [];

        const i = datos.indicadores;
        const a = datos.anterior;
        const ml = datos.modelo_ml;

        // ---------- Serie de tiempo según el período ----------
        // Hoy: por hora · 7 días: por día · 30 días: por semana
        let tramos;
        let unidadTramo;

        if (datos.periodo === 1) {
            const conActividad = datos.por_hora.filter((h) => h.pedidos > 0).map((h) => h.hora);
            const desde = conActividad.length ? Math.max(Math.min(...conActividad) - 1, 0) : 8;
            const hasta = conActividad.length ? Math.min(Math.max(...conActividad) + 1, 23) : 22;

            tramos = datos.por_hora
                .filter((h) => h.hora >= desde && h.hora <= hasta)
                .map((h) => ({ etiqueta: hora(h.hora), pedidos: h.pedidos, ventas_soles: h.ventas_soles }));
            unidadTramo = "hora";
        } else if (datos.periodo === 30) {
            tramos = agruparPorSemana(datos.por_dia);
            unidadTramo = "semana";
        } else {
            tramos = datos.por_dia.map((d) => ({ ...d, etiqueta: fechaCorta(d.dia) }));
            unidadTramo = "día";
        }

        const hayVentas = tramos.some((t) => t.pedidos > 0);
        const mejorTramo = hayVentas
            ? tramos.reduce((m, t) => (t.ventas_soles > m.ventas_soles ? t : m))
            : null;

        const entregas = datos.periodo === 30 ? tramos : datos.por_dia.map((d) => ({ ...d, etiqueta: fechaCorta(d.dia) }));
        const hayEntregas = entregas.some((d) => d.a_tiempo + d.retrasados > 0);
        const totalRetrasos = entregas.reduce((s, d) => s + d.retrasados, 0);

        const horasActivas = datos.por_hora.filter((h) => h.pedidos > 0);
        const horaPico = horasActivas.length
            ? horasActivas.reduce((m, h) => (h.pedidos > m.pedidos ? h : m))
            : null;

        const estrella = datos.productos[0];
        const evaluadosMl = ml.verdaderos_retrasos + ml.falsas_alarmas + ml.retrasos_no_detectados + ml.verdaderos_a_tiempo;
        const aciertosMl = ml.verdaderos_retrasos + ml.verdaderos_a_tiempo;

        // ---------- Frase de resumen ----------
        const resumen = i.pedidos
            ? `En <strong>${NOMBRE_PERIODO[datos.periodo]}</strong>: <strong>${i.pedidos}</strong> pedidos,
               <strong>${soles(i.ventas_soles)}</strong> en ventas
               ${i.porcentaje_a_tiempo !== null ? `y <strong>${i.porcentaje_a_tiempo} %</strong> entregados a tiempo` : ""}.
               ${horaPico ? `La hora con más pedidos fue las <strong>${hora(horaPico.hora)}</strong>.` : ""}
               ${estrella ? `Lo más vendido: <strong>${escapar(estrella.producto)}</strong>.` : ""}`
            : `No hubo pedidos en <strong>${NOMBRE_PERIODO[datos.periodo]}</strong>.`;

        // ---------- Tarjetas ----------
        const tarjetas = `
            <div class="row g-3 mb-4">
                ${tarjeta("🧾", "Pedidos", i.pedidos, comparacion(i.pedidos, a.pedidos, (v) => v))}
                ${tarjeta("💰", "Ventas", soles(i.ventas_soles), comparacion(i.ventas_soles, a.ventas_soles, (v) => soles(v, 0)))}
                ${tarjeta("🧮", "Gasto promedio por pedido", soles(i.ticket_promedio_soles),
                    comparacion(i.ticket_promedio_soles, a.ticket_promedio_soles, (v) => soles(v, 0)))}
                ${tarjeta("⏱️", "Entregados a tiempo",
                    i.porcentaje_a_tiempo === null ? "--" : `${i.porcentaje_a_tiempo} %`,
                    `<span class="dash-delta">de ${i.entregas_evaluadas} entregas</span>`)}
                ${tarjeta("🚚", "Demora real promedio",
                    i.tiempo_real_promedio_min === null ? "--" : `${i.tiempo_real_promedio_min} min`,
                    `<span class="dash-delta">se prometió ${i.tiempo_prometido_promedio_min ?? "--"} min</span>`)}
                ${tarjeta("🧠", "Aciertos del modelo ML",
                    i.porcentaje_acierto_ml === null ? "--" : `${i.porcentaje_acierto_ml} %`,
                    `<span class="dash-delta">de ${i.ml_evaluados} pedidos</span>`)}
            </div>
        `;

        // ---------- Bloque 1: ventas ----------
        const ventas = bloque(
            "💰", "Ventas",
            "Cuánto se vendió, cuándo y qué.",
            panel(
                `Ventas por ${unidadTramo} (S/)`,
                mejorTramo ? `${unidadTramo === "hora" ? "Hora" : unidadTramo === "semana" ? "Semana" : "Día"} con más ventas: <strong>${escapar(mejorTramo.etiqueta)}</strong> · ${soles(mejorTramo.ventas_soles)} (${mejorTramo.pedidos} pedidos)` : "",
                hayVentas ? lienzo("dashVentas", `Ventas por ${unidadTramo}`) : vacio()
            ) +
            panel(
                "Productos más vendidos",
                estrella ? `Producto estrella: <strong>${escapar(estrella.producto)}</strong> · ${estrella.unidades} unidades (${soles(estrella.ventas_soles)})` : "",
                datos.productos.length ? lienzo("dashProductos", "Productos más vendidos en unidades") : vacio()
            ) +
            panel(
                "¿A qué hora piden los clientes?",
                horaPico ? `Hora pico: <strong>${hora(horaPico.hora)}</strong> con ${horaPico.pedidos} pedido(s). Conviene tener cocina y repartidores listos antes.` : "",
                horasActivas.length ? lienzo("dashHoras", "Pedidos por hora del día") : vacio(),
                "col-lg-12"
            )
        );

        // ---------- Bloque 2: entregas y repartidores ----------
        const tablaRepartidores = datos.repartidores.length
            ? `
                <div class="table-responsive">
                    <table class="table table-sm align-middle mb-0 dash-tabla">
                        <thead>
                            <tr><th>Repartidor</th><th>Entregas</th><th>Con retraso</th><th>Demora promedio</th></tr>
                        </thead>
                        <tbody>
                            ${datos.repartidores.map((r) => `
                                <tr>
                                    <td><strong>${escapar(r.repartidor)}</strong></td>
                                    <td>${r.entregas}</td>
                                    <td>${r.retrasos}</td>
                                    <td>${r.tiempo_real_promedio_min ?? "--"} min</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
            `
            : vacio("Sin pedidos asignados a repartidores en este período.");

        const masEntregas = datos.repartidores[0];

        const entregasBloque = bloque(
            "🛵", "Entregas y repartidores",
            "Si los pedidos llegan a tiempo y quién los lleva.",
            panel(
                `Entregas por ${datos.periodo === 30 ? "semana" : "día"}`,
                hayEntregas
                    ? (totalRetrasos
                        ? `<strong>${totalRetrasos}</strong> entrega(s) con retraso de ${entregas.reduce((s, d) => s + d.a_tiempo + d.retrasados, 0)}.`
                        : `<strong>Todas las entregas llegaron a tiempo.</strong>`)
                    : "",
                hayEntregas ? `
                    <div class="dash-leyenda">
                        <span><i style="background:${COLOR.serie1}"></i>A tiempo</span>
                        <span><i style="background:${COLOR.serie2}"></i>Con retraso</span>
                    </div>
                    ${lienzo("dashEntregas", "Entregas a tiempo y con retraso", 206)}
                ` : vacio("Aún no hay entregas en este período.")
            ) +
            panel(
                "Repartidores",
                masEntregas ? `Más entregas: <strong>${escapar(masEntregas.repartidor)}</strong> (${masEntregas.entregas}).` : "",
                tablaRepartidores
            )
        );

        // ---------- Bloque 3: inteligencia ----------
        const fraseMl = evaluadosMl
            ? `El modelo acertó <strong>${aciertosMl} de ${evaluadosMl}</strong> pedidos.
               ${ml.retrasos_no_detectados ? `Se le escaparon <strong>${ml.retrasos_no_detectados}</strong> retraso(s).` : "No se le escapó ningún retraso."}
               ${ml.falsas_alarmas ? `Dio <strong>${ml.falsas_alarmas}</strong> falsa(s) alarma(s).` : ""}`
            : "";

        const detalleMl = evaluadosMl
            ? `
                <details class="dash-detalle">
                    <summary>Ver el detalle (matriz de confusión)</summary>
                    <table class="table table-sm table-bordered text-center mt-2 mb-0 dash-tabla">
                        <thead>
                            <tr><th></th><th>El modelo dijo: retraso</th><th>El modelo dijo: a tiempo</th></tr>
                        </thead>
                        <tbody>
                            <tr>
                                <th class="text-start">Llegó con retraso</th>
                                <td>${ml.verdaderos_retrasos} ✓</td>
                                <td>${ml.retrasos_no_detectados} ✕</td>
                            </tr>
                            <tr>
                                <th class="text-start">Llegó a tiempo</th>
                                <td>${ml.falsas_alarmas} ✕</td>
                                <td>${ml.verdaderos_a_tiempo} ✓</td>
                            </tr>
                        </tbody>
                    </table>
                </details>
                <p class="small text-secondary mt-2 mb-0">
                    Riesgo de retraso promedio que calculó el modelo: <strong>${ml.riesgo_promedio_pct ?? "--"} %</strong>.
                </p>
            `
            : vacio("Aún no hay pedidos entregados con predicción en este período.");

        const niveles = [["ALTO", "⛔"], ["MEDIO", "⚠️"], ["BAJO", "✅"]];
        const acciones = {
            PRIORIZAR_PREPARACION: "Priorizar la preparación",
            ASIGNAR_REPARTIDOR_EXTRA: "Asignar un repartidor extra",
            AJUSTAR_TIEMPO_ESTIMADO: "Ajustar el tiempo estimado",
            MONITOREAR: "Monitorear"
        };
        const totalAlertas = Object.values(datos.alertas.por_nivel).reduce((s, n) => s + n, 0);

        const bloqueAlertas = totalAlertas
            ? `
                <div class="d-flex gap-2 mb-3">
                    ${niveles.map(([n, icono]) => `
                        <div class="dash-mini">
                            <div class="dash-tarjeta-titulo">${icono} Riesgo ${n.toLowerCase()}</div>
                            <div class="fs-5 fw-bold">${datos.alertas.por_nivel[n] || 0}</div>
                        </div>
                    `).join("")}
                </div>
                <table class="table table-sm mb-0 dash-tabla">
                    <thead><tr><th>Lo que recomendaron los agentes</th><th>Veces</th></tr></thead>
                    <tbody>
                        ${Object.entries(datos.alertas.por_accion)
                            .sort((x, y) => y[1] - x[1])
                            .map(([accion, n]) => `<tr><td>${escapar(acciones[accion] || accion)}</td><td>${n}</td></tr>`)
                            .join("")}
                    </tbody>
                </table>
            `
            : vacio("Los agentes no analizaron pedidos en este período.");

        const inteligencia = bloque(
            "🧠", "Inteligencia del sistema",
            "Qué tan bien predice el modelo ML y qué hicieron los agentes.",
            panel("Modelo de Machine Learning", fraseMl, detalleMl) +
            panel(
                "Agentes: pedidos en riesgo",
                totalAlertas ? `Los agentes analizaron <strong>${totalAlertas}</strong> pedido(s) con riesgo de retraso.` : "",
                bloqueAlertas
            )
        );

        contenido.innerHTML = `
            <div class="dash-resumen">${resumen}</div>
            ${tarjetas}
            ${ventas}
            ${entregasBloque}
            ${inteligencia}
        `;

        // ---------- Gráficos ----------
        if (hayVentas) {
            const opciones = opcionesBase({ valores: tramos.length <= 14, formato: (v) => `S/ ${Math.round(v)}` });

            opciones.plugins.tooltip.callbacks = {
                label: (c) => ` ${soles(c.parsed.y)} · ${tramos[c.dataIndex].pedidos} pedido(s)`
            };

            crearGrafico("dashVentas", {
                type: "bar",
                data: {
                    labels: tramos.map((t) => t.etiqueta),
                    datasets: [{ label: "Ventas", data: tramos.map((t) => t.ventas_soles), ...barras(COLOR.serie1) }]
                },
                options: opciones
            });
        }

        if (datos.productos.length) {
            const opciones = opcionesBase({ horizontal: true, valores: true, formato: (v) => `${v} u.` });

            opciones.plugins.tooltip.callbacks = {
                label: (c) => ` ${c.parsed.x} unidades · ${soles(datos.productos[c.dataIndex].ventas_soles)}`
            };

            crearGrafico("dashProductos", {
                type: "bar",
                data: {
                    labels: datos.productos.map((p) => p.producto),
                    datasets: [{ label: "Unidades", data: datos.productos.map((p) => p.unidades), ...barras(COLOR.serie1) }]
                },
                options: opciones
            });
        }

        if (horasActivas.length) {
            const activas = horasActivas.map((h) => h.hora);
            const desde = Math.max(Math.min(...activas) - 1, 0);
            const hasta = Math.min(Math.max(...activas) + 1, 23);
            const horas = datos.por_hora.filter((h) => h.hora >= desde && h.hora <= hasta);

            crearGrafico("dashHoras", {
                type: "bar",
                data: {
                    labels: horas.map((h) => hora(h.hora)),
                    datasets: [{ label: "Pedidos", data: horas.map((h) => h.pedidos), ...barras(COLOR.serie1) }]
                },
                options: opcionesBase({ valores: true })
            });
        }

        if (hayEntregas) {
            crearGrafico("dashEntregas", {
                type: "bar",
                data: {
                    labels: entregas.map((d) => d.etiqueta),
                    datasets: [
                        { label: "A tiempo", data: entregas.map((d) => d.a_tiempo), ...barras(COLOR.serie1) },
                        { label: "Con retraso", data: entregas.map((d) => d.retrasados), ...barras(COLOR.serie2) }
                    ]
                },
                options: opcionesBase({ apiladas: true, valores: entregas.length <= 14 })
            });
        }
    }


    async function cargar() {

        contenido.innerHTML = `<p class="text-secondary">Cargando...</p>`;

        filtros.querySelectorAll("button").forEach((b) => {
            b.classList.toggle("active", Number(b.dataset.periodo) === periodo);
        });

        try {

            const respuesta = await fetch(`/api/dashboard?periodo=${periodo}`, {
                headers: {
                    "Authorization": `Bearer ${localStorage.getItem("kimbos_admin_token")}`
                }
            });

            const datos = await respuesta.json();

            if (!respuesta.ok || !datos.ok) {
                throw new Error(datos.mensaje || "No se pudo cargar el dashboard.");
            }

            pintar(datos);

        } catch (error) {
            contenido.innerHTML = `<div class="alert alert-danger">${escapar(error.message)}</div>`;
        }
    }


    filtros.addEventListener("click", (evento) => {

        const boton = evento.target.closest("button[data-periodo]");

        if (!boton) {
            return;
        }

        periodo = Number(boton.dataset.periodo);
        cargar();
    });

    modal.addEventListener("show.bs.modal", cargar);

})();

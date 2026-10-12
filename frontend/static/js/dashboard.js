/* ========================================================
   DASHBOARD DEL ADMINISTRADOR (solo lectura)
   Indicadores y gráficos del período: hoy, 7 o 30 días.
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

    let periodo = 7;
    let graficos = [];


    function escapar(valor) {

        return String(valor ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }


    function soles(valor) {
        return valor === null || valor === undefined ? "--" : `S/ ${Number(valor).toFixed(2)}`;
    }


    function fechaCorta(iso) {
        const [, mes, dia] = iso.split("-");
        return `${dia}/${mes}`;
    }


    /* Variación frente al período anterior. mejorSiSube: si subir es bueno. */
    function variacion(actual, anterior, mejorSiSube = true, unidad = "%") {

        if (actual === null || actual === undefined || anterior === null || anterior === undefined) {
            return `<span class="dash-delta">sin datos del período anterior</span>`;
        }

        let cambio;
        let texto;

        if (unidad === "%") {
            if (!anterior) {
                return `<span class="dash-delta">sin datos del período anterior</span>`;
            }
            cambio = ((actual - anterior) / anterior) * 100;
            texto = `${Math.abs(cambio).toFixed(0)} %`;
        } else {
            cambio = actual - anterior;
            texto = `${Math.abs(cambio).toFixed(1)} ${unidad}`;
        }

        if (Math.abs(cambio) < 0.05) {
            return `<span class="dash-delta">= igual que el período anterior</span>`;
        }

        const sube = cambio > 0;
        const bueno = sube === mejorSiSube;

        return `
            <span class="dash-delta" style="color: ${bueno ? COLOR.subeBien : COLOR.bajaMal}">
                ${sube ? "▲" : "▼"} ${texto}
            </span>
            <span class="dash-delta">vs período anterior</span>
        `;
    }


    function tarjeta(titulo, valor, detalle) {

        return `
            <div class="col-6 col-lg-4 col-xl-2">
                <div class="dash-tarjeta">
                    <div class="dash-tarjeta-titulo">${titulo}</div>
                    <div class="dash-tarjeta-valor">${valor}</div>
                    <div>${detalle}</div>
                </div>
            </div>
        `;
    }


    function seccion(titulo, cuerpo, columnas = "col-lg-6") {

        return `
            <div class="col-12 ${columnas}">
                <div class="dash-panel">
                    <h6 class="dash-panel-titulo">${titulo}</h6>
                    ${cuerpo}
                </div>
            </div>
        `;
    }


    function lienzo(id, etiqueta, alto = 240) {

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
    function opcionesBase(extra = {}) {

        return {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: "#0b0b0b",
                    titleColor: "#ffffff",
                    bodyColor: "#ffffff",
                    padding: 10,
                    cornerRadius: 8
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    border: { color: "#c3c2b7" },
                    ticks: { color: COLOR.apagado, font: { size: 11 } }
                },
                y: {
                    beginAtZero: true,
                    grid: { color: COLOR.grilla },
                    border: { display: false },
                    ticks: { color: COLOR.apagado, font: { size: 11 }, precision: 0 }
                }
            },
            ...extra
        };
    }


    function barras(color) {

        return {
            backgroundColor: color,
            borderColor: COLOR.superficie,
            borderWidth: 2,
            borderSkipped: "start",
            borderRadius: 4,
            maxBarThickness: 28
        };
    }


    function crearGrafico(id, configuracion) {

        const elemento = document.getElementById(id);

        if (elemento && window.Chart) {
            graficos.push(new Chart(elemento, configuracion));
        }
    }


    function pintar(datos) {

        graficos.forEach((g) => g.destroy());
        graficos = [];

        const i = datos.indicadores;
        const a = datos.anterior;
        const ml = datos.modelo_ml;

        const hayDias = datos.por_dia.some((d) => d.pedidos > 0);
        const hayEntregas = datos.por_dia.some((d) => d.a_tiempo + d.retrasados > 0);
        const hayHoras = datos.por_hora.some((h) => h.pedidos > 0);
        const evaluadosMl = ml.verdaderos_retrasos + ml.falsas_alarmas + ml.retrasos_no_detectados + ml.verdaderos_a_tiempo;

        // ---------- Indicadores ----------
        const tarjetas = `
            <div class="row g-3 mb-3">
                ${tarjeta("Pedidos", i.pedidos, variacion(i.pedidos, a.pedidos))}
                ${tarjeta("Ventas", soles(i.ventas_soles), variacion(i.ventas_soles, a.ventas_soles))}
                ${tarjeta("Ticket promedio", soles(i.ticket_promedio_soles), variacion(i.ticket_promedio_soles, a.ticket_promedio_soles))}
                ${tarjeta(
                    "Entregas a tiempo",
                    i.porcentaje_a_tiempo === null ? "--" : `${i.porcentaje_a_tiempo} %`,
                    `<span class="dash-delta">${i.entregas_evaluadas} entregas evaluadas</span>`
                )}
                ${tarjeta(
                    "Tiempo real promedio",
                    i.tiempo_real_promedio_min === null ? "--" : `${i.tiempo_real_promedio_min} min`,
                    `<span class="dash-delta">prometido: ${i.tiempo_prometido_promedio_min ?? "--"} min</span>`
                )}
                ${tarjeta(
                    "Acierto del modelo ML",
                    i.porcentaje_acierto_ml === null ? "--" : `${i.porcentaje_acierto_ml} %`,
                    `<span class="dash-delta">${i.ml_evaluados} predicciones evaluadas</span>`
                )}
            </div>
        `;

        // ---------- Repartidores (tabla) ----------
        const tablaRepartidores = datos.repartidores.length
            ? `
                <div class="table-responsive">
                    <table class="table table-sm align-middle mb-0 dash-tabla">
                        <thead>
                            <tr><th>Repartidor</th><th>Entregas</th><th>Retrasos</th><th>Tiempo real prom.</th></tr>
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

        // ---------- Modelo ML (matriz de confusión) ----------
        const matrizMl = evaluadosMl
            ? `
                <table class="table table-sm table-bordered text-center mb-2 dash-tabla">
                    <thead>
                        <tr><th></th><th>Predijo: Retrasado</th><th>Predijo: A tiempo</th></tr>
                    </thead>
                    <tbody>
                        <tr>
                            <th class="text-start">Real: Retrasado</th>
                            <td><strong>${ml.verdaderos_retrasos}</strong><br><small class="text-secondary">detectados</small></td>
                            <td><strong>${ml.retrasos_no_detectados}</strong><br><small class="text-secondary">no detectados</small></td>
                        </tr>
                        <tr>
                            <th class="text-start">Real: A tiempo</th>
                            <td><strong>${ml.falsas_alarmas}</strong><br><small class="text-secondary">falsas alarmas</small></td>
                            <td><strong>${ml.verdaderos_a_tiempo}</strong><br><small class="text-secondary">correctos</small></td>
                        </tr>
                    </tbody>
                </table>
                <p class="small text-secondary mb-0">
                    Riesgo promedio estimado: <strong>${ml.riesgo_promedio_pct ?? "--"} %</strong>
                    · ${evaluadosMl} pedidos entregados con predicción.
                </p>
            `
            : vacio("Aún no hay pedidos entregados con predicción en este período.");

        // ---------- Multiagente ----------
        const niveles = ["ALTO", "MEDIO", "BAJO"];
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
                    ${niveles.map((n) => `
                        <div class="dash-mini">
                            <div class="dash-tarjeta-titulo">Riesgo ${n.toLowerCase()}</div>
                            <div class="fs-5 fw-bold">${datos.alertas.por_nivel[n] || 0}</div>
                        </div>
                    `).join("")}
                </div>
                <table class="table table-sm mb-0 dash-tabla">
                    <thead><tr><th>Acción recomendada por los agentes</th><th>Veces</th></tr></thead>
                    <tbody>
                        ${Object.entries(datos.alertas.por_accion)
                            .sort((x, y) => y[1] - x[1])
                            .map(([accion, n]) => `<tr><td>${escapar(acciones[accion] || accion)}</td><td>${n}</td></tr>`)
                            .join("")}
                    </tbody>
                </table>
            `
            : vacio("Los agentes no analizaron pedidos en este período.");

        contenido.innerHTML = `
            <p class="small text-secondary mb-3">
                Del ${fechaCorta(datos.desde)} al ${fechaCorta(datos.hasta)} · solo pedidos reales.
            </p>

            ${tarjetas}

            <div class="row g-3">
                ${seccion("Ventas por día (S/)", hayDias ? lienzo("dashVentas", "Ventas por día en soles") : vacio())}
                ${seccion("Entregas por día: a tiempo y retrasadas", hayEntregas ? `
                    <div class="dash-leyenda">
                        <span><i style="background:${COLOR.serie1}"></i>A tiempo</span>
                        <span><i style="background:${COLOR.serie2}"></i>Retrasadas</span>
                    </div>
                    ${lienzo("dashEntregas", "Entregas a tiempo y retrasadas por día", 216)}
                ` : vacio("Aún no hay entregas en este período."))}
                ${seccion("Pedidos por hora del día", hayHoras ? lienzo("dashHoras", "Pedidos por hora del día") : vacio())}
                ${seccion("Productos más vendidos (unidades)", datos.productos.length ? lienzo("dashProductos", "Productos más vendidos en unidades") : vacio())}
                ${seccion("Repartidores", tablaRepartidores)}
                ${seccion("Modelo ML en pedidos reales", matrizMl)}
                ${seccion("Sistema multiagente: alertas de pedidos en riesgo", bloqueAlertas, "col-lg-12")}
            </div>
        `;

        // ---------- Gráficos ----------
        if (hayDias) {
            crearGrafico("dashVentas", {
                type: "bar",
                data: {
                    labels: datos.por_dia.map((d) => fechaCorta(d.dia)),
                    datasets: [{
                        label: "Ventas",
                        data: datos.por_dia.map((d) => d.ventas_soles),
                        ...barras(COLOR.serie1)
                    }]
                },
                options: opcionesBase({
                    plugins: {
                        ...opcionesBase().plugins,
                        tooltip: {
                            ...opcionesBase().plugins.tooltip,
                            callbacks: {
                                label: (c) => {
                                    const dia = datos.por_dia[c.dataIndex];
                                    return ` ${soles(c.parsed.y)} · ${dia.pedidos} pedido(s)`;
                                }
                            }
                        }
                    }
                })
            });
        }

        if (hayEntregas) {
            const opciones = opcionesBase();
            opciones.scales.x.stacked = true;
            opciones.scales.y.stacked = true;

            crearGrafico("dashEntregas", {
                type: "bar",
                data: {
                    labels: datos.por_dia.map((d) => fechaCorta(d.dia)),
                    datasets: [
                        { label: "A tiempo", data: datos.por_dia.map((d) => d.a_tiempo), ...barras(COLOR.serie1) },
                        { label: "Retrasadas", data: datos.por_dia.map((d) => d.retrasados), ...barras(COLOR.serie2) }
                    ]
                },
                options: opciones
            });
        }

        if (hayHoras) {
            // Solo el tramo de horas con actividad (más una hora a cada lado)
            const conPedidos = datos.por_hora.filter((h) => h.pedidos > 0).map((h) => h.hora);
            const desde = Math.max(Math.min(...conPedidos) - 1, 0);
            const hasta = Math.min(Math.max(...conPedidos) + 1, 23);
            const horas = datos.por_hora.filter((h) => h.hora >= desde && h.hora <= hasta);

            crearGrafico("dashHoras", {
                type: "bar",
                data: {
                    labels: horas.map((h) => `${String(h.hora).padStart(2, "0")}h`),
                    datasets: [{ label: "Pedidos", data: horas.map((h) => h.pedidos), ...barras(COLOR.serie1) }]
                },
                options: opcionesBase()
            });
        }

        if (datos.productos.length) {
            const opciones = opcionesBase({ indexAxis: "y" });
            opciones.scales = {
                x: {
                    beginAtZero: true,
                    grid: { color: COLOR.grilla },
                    border: { display: false },
                    ticks: { color: COLOR.apagado, font: { size: 11 }, precision: 0 }
                },
                y: {
                    grid: { display: false },
                    border: { color: "#c3c2b7" },
                    ticks: { color: COLOR.texto, font: { size: 12 } }
                }
            };
            opciones.plugins.tooltip.callbacks = {
                label: (c) => ` ${c.parsed.x} unidades · ${soles(datos.productos[c.dataIndex].ventas_soles)}`
            };

            crearGrafico("dashProductos", {
                type: "bar",
                data: {
                    labels: datos.productos.map((p) => p.producto),
                    datasets: [{
                        label: "Unidades",
                        data: datos.productos.map((p) => p.unidades),
                        ...barras(COLOR.serie1),
                        borderSkipped: "start"
                    }]
                },
                options: opciones
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

/* ========================================================
   REPORTE DIARIO (sistema multiagente)
   Analista de datos -> Estratega -> Redactor
======================================================== */

(function () {

    const modal = document.getElementById("modalReporteDiario");
    const contenido = document.getElementById("contenidoReporte");
    const selector = document.getElementById("selectorReporte");
    const botonGenerar = document.getElementById("btnGenerarReporte");

    if (!modal) {
        return;
    }

    let reportes = [];


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


    function tarjeta(titulo, valor, detalle = "") {

        return `
            <div class="col-6 col-lg">
                <div class="border rounded-3 p-3 h-100 bg-white">
                    <small class="text-secondary">${titulo}</small>
                    <div class="fs-4 fw-bold">${valor}</div>
                    <small class="text-secondary">${detalle}</small>
                </div>
            </div>
        `;
    }


    function porcentaje(valor) {
        return valor === null || valor === undefined ? "--" : `${valor} %`;
    }


    function pintar(reporte) {

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

        const m = reporte.metricas || {};
        const ml = m.modelo_ml || {};

        const colores = { ALTA: "bg-danger", MEDIA: "bg-warning text-dark", BAJA: "bg-secondary" };

        const hallazgos = (reporte.hallazgos || [])
            .map((h) => `<li class="mb-1">${escapar(h)}</li>`)
            .join("");

        const recomendaciones = (reporte.recomendaciones || [])
            .map((r) => `
                <div class="border rounded-3 p-3 mb-2 bg-white">
                    <div class="d-flex justify-content-between gap-2">
                        <strong>${escapar(r.titulo)}</strong>
                        <span class="badge ${colores[r.prioridad] || "bg-secondary"}">${escapar(r.prioridad)}</span>
                    </div>
                    <div class="text-secondary small mt-1">${escapar(r.detalle)}</div>
                </div>
            `)
            .join("") || `<p class="text-secondary">Sin recomendaciones.</p>`;

        const productos = (m.productos_mas_vendidos || [])
            .map((p) => `<li>${escapar(p.producto)} <strong>× ${p.unidades}</strong></li>`)
            .join("") || "<li class='text-secondary'>Sin ventas</li>";

        contenido.innerHTML = `
            <div class="reporte-resumen mb-4">
                <div class="reporte-resumen-etiqueta">
                    3 · Agente Redactor: resumen ejecutivo
                </div>
                <h5 class="fw-bold mb-1">${escapar(reporte.titulo)}</h5>
                <p class="mb-0">${escapar(reporte.resumen)}</p>
            </div>

            <div class="row g-3 mb-4">
                ${tarjeta("Pedidos", m.pedidos ?? 0, `${m.entregados ?? 0} entregados · ${m.cancelados ?? 0} cancelados`)}
                ${tarjeta("Ventas", `S/ ${Number(m.ventas_soles || 0).toFixed(2)}`, `Ticket S/ ${Number(m.ticket_promedio_soles || 0).toFixed(2)}`)}
                ${tarjeta("Retrasos reales", porcentaje(m.porcentaje_retrasos), `${m.entregas_con_retraso ?? 0} de ${m.entregas_evaluadas ?? 0} entregas`)}
                ${tarjeta("Acierto del modelo ML", porcentaje(ml.porcentaje_acierto), `${ml.aciertos ?? 0} de ${ml.predicciones_evaluadas ?? 0} predicciones`)}
                ${tarjeta("Repartidores para mañana", reporte.repartidores_sugeridos ?? "--", `hoy: ${m.repartidores_disponibles ?? "--"}`)}
            </div>

            <div class="row g-4">
                <div class="col-lg-6">
                    <h6 class="fw-bold">1 · Agente Analista de datos: hallazgos</h6>
                    <ul class="ps-3">${hallazgos}</ul>

                    <h6 class="fw-bold mt-3">Productos más vendidos</h6>
                    <ul class="ps-3">${productos}</ul>
                </div>

                <div class="col-lg-6">
                    <h6 class="fw-bold">2 · Agente Estratega: recomendaciones para mañana</h6>
                    ${recomendaciones}
                </div>
            </div>

            <p class="text-secondary small mt-3 mb-0">
                ${reporte.origen === "PROGRAMADO" ? "Generado automáticamente (Cloud Scheduler)" : "Generado manualmente"}
            </p>
        `;
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
        botonGenerar.textContent = "🤖 Los agentes están trabajando (≈30 s)…";

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


    selector.addEventListener("change", () => pintar(reportes[Number(selector.value)]));
    botonGenerar.addEventListener("click", generar);
    modal.addEventListener("show.bs.modal", cargar);

})();

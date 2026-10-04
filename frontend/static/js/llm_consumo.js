/* ========================================================
   PANEL "CONSUMO DEL LLM" (admin)
======================================================== */

(function () {

    const modal = document.getElementById("modalConsumoLLM");
    const contenido = document.getElementById("contenidoConsumoLLM");

    if (!modal || !contenido) {
        return;
    }


    function escapar(valor) {

        return String(valor ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }


    function usd(valor, decimales = 4) {
        return `$${Number(valor || 0).toFixed(decimales)}`;
    }


    function tarjeta(titulo, valor, detalle = "") {

        return `
            <div class="col-6 col-lg-3">
                <div class="border rounded-3 p-3 h-100 bg-white">
                    <small class="text-secondary">${titulo}</small>
                    <div class="fs-4 fw-bold">${valor}</div>
                    <small class="text-secondary">${detalle}</small>
                </div>
            </div>
        `;
    }


    function estadoAsistente(nombre, activo, corte) {

        return `
            <span class="badge ${activo ? "bg-success" : "bg-danger"} me-2">
                ${nombre}: ${activo ? "activo" : "en pausa"} (corte ${usd(corte, 2)})
            </span>
        `;
    }


    function pintar(datos) {

        const porcentaje = datos.presupuesto_usd
            ? Math.min((datos.gasto_mes_usd / datos.presupuesto_usd) * 100, 100)
            : 0;

        const claseBarra = porcentaje >= 80
            ? "peligro"
            : porcentaje >= 50 ? "alerta" : "";

        const cliente = datos.por_asistente.CLIENTE || {};
        const admin = datos.por_asistente.ADMIN || {};

        const filasAsistente = [["Cliente", cliente], ["Admin", admin]]
            .map(([nombre, a]) => `
                <tr>
                    <td>${nombre}</td>
                    <td>${a.mensajes || 0}</td>
                    <td>${(a.tokens_entrada || 0).toLocaleString()}</td>
                    <td>${(a.tokens_cache || 0).toLocaleString()}</td>
                    <td>${(a.tokens_salida || 0).toLocaleString()}</td>
                    <td>${a.errores || 0}</td>
                    <td class="fw-bold">${usd(a.costo_usd)}</td>
                </tr>
            `).join("");

        const filasUltimos = datos.ultimos.length
            ? datos.ultimos.map((u) => `
                <tr class="${u.ok ? "" : "table-danger"}">
                    <td>${escapar(u.fecha)}</td>
                    <td>${escapar(u.asistente)}</td>
                    <td>${escapar(u.usuario)}</td>
                    <td>${u.tokens_entrada} / ${u.tokens_cache} / ${u.tokens_salida}</td>
                    <td>${u.pasos}</td>
                    <td><small>${escapar(u.herramientas || "-")}</small></td>
                    <td>${u.duracion_ms ? (u.duracion_ms / 1000).toFixed(1) + " s" : "-"}</td>
                    <td>${usd(u.costo_usd, 6)}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="8" class="text-secondary">Aún no hay consultas registradas.</td></tr>`;

        const filasDias = datos.por_dia.length
            ? datos.por_dia.map((d) => `
                <tr>
                    <td>${escapar(d.dia)}</td>
                    <td>${d.mensajes}</td>
                    <td>${usd(d.costo_usd)}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="3" class="text-secondary">Sin datos.</td></tr>`;

        contenido.innerHTML = `
            ${datos.configurado ? "" : `
                <div class="alert alert-warning">
                    Falta configurar <code>OPENAI_API_KEY</code> en el servidor: los asistentes están apagados.
                </div>`}

            <div class="mb-3">
                <div class="d-flex justify-content-between mb-1">
                    <strong>Gasto del mes: ${usd(datos.gasto_mes_usd)} de ${usd(datos.presupuesto_usd, 2)}</strong>
                    <span class="text-secondary">${porcentaje.toFixed(1)} %</span>
                </div>
                <div class="llm-barra">
                    <div class="${claseBarra}" style="width: ${porcentaje}%"></div>
                </div>
                <div class="mt-2">
                    ${estadoAsistente("Cliente", datos.cliente_activo, datos.corte_cliente_usd)}
                    ${estadoAsistente("Admin", datos.admin_activo, datos.corte_admin_usd)}
                </div>
            </div>

            <div class="row g-3 mb-4">
                ${tarjeta("Mensajes del mes", datos.mensajes_mes)}
                ${tarjeta("Costo promedio", usd(datos.costo_promedio_usd, 6), "por mensaje")}
                ${tarjeta("Modelo", escapar(datos.modelo),
                    `USD/millón: ${datos.precios_usd_millon.entrada} entrada · ${datos.precios_usd_millon.cache} caché · ${datos.precios_usd_millon.salida} salida`)}
                ${tarjeta("Límites", `${datos.limites_diarios.CLIENTE} / día`,
                    `por cliente · máx. ${datos.max_pasos} pasos y ${datos.max_tokens_salida} tokens de salida`)}
            </div>

            <h6 class="fw-bold">Por asistente (mes actual)</h6>
            <div class="table-responsive mb-4">
                <table class="table table-sm align-middle">
                    <thead>
                        <tr>
                            <th>Asistente</th><th>Mensajes</th><th>Tokens entrada</th>
                            <th>En caché</th><th>Tokens salida</th><th>Errores</th><th>Costo</th>
                        </tr>
                    </thead>
                    <tbody>${filasAsistente}</tbody>
                </table>
            </div>

            <div class="row g-4">
                <div class="col-lg-8">
                    <h6 class="fw-bold">Últimas consultas</h6>
                    <div class="table-responsive">
                        <table class="table table-sm align-middle">
                            <thead>
                                <tr>
                                    <th>Fecha</th><th>Asistente</th><th>Usuario</th>
                                    <th>Tokens (ent / caché / sal)</th><th>Pasos</th>
                                    <th>Herramientas</th><th>Tiempo</th><th>Costo</th>
                                </tr>
                            </thead>
                            <tbody>${filasUltimos}</tbody>
                        </table>
                    </div>
                </div>

                <div class="col-lg-4">
                    <h6 class="fw-bold">Últimos 14 días</h6>
                    <table class="table table-sm">
                        <thead><tr><th>Día</th><th>Mensajes</th><th>Costo</th></tr></thead>
                        <tbody>${filasDias}</tbody>
                    </table>
                </div>
            </div>
        `;
    }


    async function cargar() {

        contenido.innerHTML = `<p class="text-secondary">Cargando...</p>`;

        try {

            const respuesta = await fetch("/api/asistente/consumo", {
                headers: {
                    "Authorization":
                        `Bearer ${localStorage.getItem("kimbos_admin_token")}`
                }
            });

            const datos = await respuesta.json();

            if (!respuesta.ok || !datos.ok) {
                throw new Error(datos.mensaje || "No se pudo cargar el consumo.");
            }

            pintar(datos);

        } catch (error) {

            contenido.innerHTML = `
                <div class="alert alert-danger">${escapar(error.message)}</div>
            `;
        }
    }


    modal.addEventListener("show.bs.modal", cargar);

})();

/* ========================================================
   PERSONAL Y CLIENTES (solo ADMIN) Y CAMBIO DE CONTRASEÑA
   - Crear administradores u operadores, activarlos o
     desactivarlos y restablecer su contraseña.
   - Cualquier miembro del personal cambia su contraseña.
======================================================== */

(function () {

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


    async function pedir(url, opciones = {}) {

        const respuesta = await fetch(url, { headers: cabeceras(), ...opciones });
        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "No se pudo completar la acción.");
        }

        return datos;
    }


    /* ---------- Lista del personal ---------- */

    async function cargarPersonal() {

        const contenedor = document.getElementById("listaPersonal");
        contenedor.innerHTML = `<p class="text-secondary">Cargando...</p>`;

        try {

            const { personal } = await pedir("/api/personal");

            contenedor.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-sm align-middle">
                        <thead>
                            <tr>
                                <th>Nombre</th><th>Correo</th><th>Rol</th>
                                <th>Activo</th><th>Contraseña</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${personal.map((p) => `
                                <tr class="${p.activo ? "" : "text-secondary"}">
                                    <td>
                                        <strong>${escapar(p.nombre)}</strong>
                                        ${p.soy_yo ? `<span class="badge bg-secondary ms-1">Tú</span>` : ""}
                                    </td>
                                    <td>${escapar(p.correo)}</td>
                                    <td>${p.rol === "ADMIN" ? "Administrador" : "Operador"}</td>
                                    <td>
                                        <div class="form-check form-switch m-0">
                                            <input class="form-check-input" type="checkbox"
                                                ${p.activo ? "checked" : ""} ${p.soy_yo ? "disabled" : ""}
                                                onchange="activarPersonal(${p.id}, this)">
                                        </div>
                                    </td>
                                    <td>
                                        ${p.soy_yo
                                            ? `<span class="small text-secondary">Usa “🔑 Contraseña”</span>`
                                            : `<button class="btn btn-sm btn-outline-dark" type="button"
                                                onclick="restablecerPassword(${p.id}, '${escapar(p.nombre)}')">
                                                Restablecer
                                              </button>`}
                                    </td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
                <p class="small text-secondary mb-0">
                    Los repartidores se gestionan en “🛵 Repartidores”.
                </p>
            `;

        } catch (error) {
            contenedor.innerHTML = `<div class="alert alert-danger">${escapar(error.message)}</div>`;
        }
    }


    window.activarPersonal = async function (usuarioId, interruptor) {

        try {
            await pedir(`/api/personal/${usuarioId}`, {
                method: "PATCH",
                body: JSON.stringify({ activo: interruptor.checked })
            });
            await cargarPersonal();
        } catch (error) {
            interruptor.checked = !interruptor.checked;
            alert(error.message);
        }
    };


    window.restablecerPassword = async function (usuarioId, nombre) {

        const nueva = prompt(`Nueva contraseña para ${nombre} (mínimo 8 caracteres):`);

        if (nueva === null) {
            return;
        }

        try {
            const datos = await pedir(`/api/personal/${usuarioId}/password`, {
                method: "PATCH",
                body: JSON.stringify({ password: nueva })
            });
            alert(`${datos.mensaje}. Comunícasela a ${nombre} de forma privada.`);
        } catch (error) {
            alert(error.message);
        }
    };


    async function crearPersonal(evento) {

        evento.preventDefault();

        const formulario = evento.target;
        const boton = formulario.querySelector("button[type=submit]");
        boton.disabled = true;

        try {

            const datos = await pedir("/api/personal", {
                method: "POST",
                body: JSON.stringify({
                    nombre: formulario.nombre.value,
                    correo: formulario.correo.value,
                    telefono: formulario.telefono.value,
                    rol: formulario.rol.value,
                    password: formulario.password.value
                })
            });

            formulario.reset();
            alert(datos.mensaje);
            await cargarPersonal();

        } catch (error) {
            alert(error.message);
        } finally {
            boton.disabled = false;
        }
    }


    /* ---------- Clientes registrados (solo lectura) ---------- */

    const soles = (monto) => `S/ ${Number(monto || 0).toFixed(2)}`;

    function fechaCorta(iso) {
        return iso
            ? new Date(iso).toLocaleDateString("es-PE", { day: "2-digit", month: "short", year: "numeric" })
            : "—";
    }

    let busquedaClientes = null;

    async function cargarClientes() {

        const contenedor = document.getElementById("listaClientes");
        const buscar = document.getElementById("buscarCliente").value.trim();

        try {

            const { clientes, total } = await pedir(
                `/api/personal/clientes?buscar=${encodeURIComponent(buscar)}`
            );

            const conCompras = clientes.filter((c) => c.entregados > 0).length;

            document.getElementById("resumenClientes").textContent = buscar
                ? `${clientes.length} resultado(s).`
                : `${total} clientes registrados · ${conCompras} con al menos una compra entregada.`;

            if (!clientes.length) {
                contenedor.innerHTML = `<p class="text-secondary">No hay clientes que coincidan.</p>`;
                return;
            }

            contenedor.innerHTML = `
                <div class="table-responsive">
                    <table class="table table-sm align-middle">
                        <thead>
                            <tr>
                                <th>Cliente</th><th>Teléfono</th><th>Registrado</th>
                                <th class="text-end">Pedidos</th><th class="text-end">Comprado</th>
                                <th>Último pedido</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${clientes.map((c) => `
                                <tr class="${c.activo ? "" : "text-secondary"}">
                                    <td>
                                        <strong>${escapar(c.nombre)}</strong>
                                        ${c.activo ? "" : `<span class="badge bg-secondary ms-1">Inactivo</span>`}
                                        <div class="small text-secondary">${escapar(c.correo)}</div>
                                    </td>
                                    <td>${escapar(c.telefono || "—")}</td>
                                    <td>${fechaCorta(c.registrado)}</td>
                                    <td class="text-end">
                                        ${c.pedidos}
                                        <div class="small text-secondary">${c.entregados} entregado(s)</div>
                                    </td>
                                    <td class="text-end fw-semibold">${soles(c.total_comprado)}</td>
                                    <td>${c.ultimo_pedido ? fechaCorta(c.ultimo_pedido) : `<span class="text-secondary">Sin pedidos</span>`}</td>
                                </tr>
                            `).join("")}
                        </tbody>
                    </table>
                </div>
                <p class="small text-secondary mb-0">
                    “Comprado” suma solo los pedidos entregados. Los cancelados no se cuentan.
                </p>
            `;

        } catch (error) {
            contenedor.innerHTML = `<div class="alert alert-danger">${escapar(error.message)}</div>`;
        }
    }


    /* ---------- Mi contraseña ---------- */

    async function cambiarMiPassword(evento) {

        evento.preventDefault();

        const formulario = evento.target;
        const mensaje = document.getElementById("mensajeMiPassword");

        if (formulario.nueva.value !== formulario.confirmar.value) {
            mensaje.className = "alert alert-warning py-2";
            mensaje.textContent = "La confirmación no coincide con la nueva contraseña.";
            return;
        }

        try {

            const datos = await pedir("/api/auth/cambiar-password", {
                method: "POST",
                body: JSON.stringify({
                    actual: formulario.actual.value,
                    nueva: formulario.nueva.value
                })
            });

            formulario.reset();
            mensaje.className = "alert alert-success py-2";
            mensaje.textContent = datos.mensaje;

        } catch (error) {
            mensaje.className = "alert alert-danger py-2";
            mensaje.textContent = error.message;
        }
    }


    /* ---------- Solo el ADMIN ve "Personal" y "Clientes" ---------- */

    function mostrarSegunRol() {

        const esAdmin = typeof usuarioAdmin !== "undefined" && usuarioAdmin && usuarioAdmin.rol === "ADMIN";

        ["btnPersonal", "btnClientes"].forEach((id) => {
            const boton = document.getElementById(id);
            if (boton) {
                boton.classList.toggle("d-none", !esAdmin);
            }
        });
    }


    document.addEventListener("DOMContentLoaded", () => {

        const modalPersonal = document.getElementById("modalPersonal");
        const formularioPersonal = document.getElementById("formPersonal");
        const modalPassword = document.getElementById("modalMiPassword");
        const formularioPassword = document.getElementById("formMiPassword");

        if (modalPersonal) {
            modalPersonal.addEventListener("show.bs.modal", cargarPersonal);
        }

        if (formularioPersonal) {
            formularioPersonal.addEventListener("submit", crearPersonal);
        }

        const modalClientes = document.getElementById("modalClientes");

        if (modalClientes) {

            modalClientes.addEventListener("show.bs.modal", () => {
                document.getElementById("buscarCliente").value = "";
                document.getElementById("listaClientes").innerHTML = `<p class="text-secondary">Cargando...</p>`;
                cargarClientes();
            });

            // Busca mientras se escribe (espera a que se deje de teclear)
            document.getElementById("buscarCliente").addEventListener("input", () => {
                clearTimeout(busquedaClientes);
                busquedaClientes = setTimeout(cargarClientes, 350);
            });
        }

        if (modalPassword) {
            modalPassword.addEventListener("show.bs.modal", () => {
                formularioPassword.reset();
                document.getElementById("mensajeMiPassword").className = "d-none";
            });
        }

        if (formularioPassword) {
            formularioPassword.addEventListener("submit", cambiarMiPassword);
        }

        // El perfil del admin se carga despues del login
        mostrarSegunRol();
        setInterval(mostrarSegunRol, 1500);
    });

})();

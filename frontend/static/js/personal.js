/* ========================================================
   PERSONAL (solo ADMIN) Y CAMBIO DE CONTRASEÑA
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


    /* ---------- Solo el ADMIN ve "Personal" ---------- */

    function mostrarSegunRol() {

        const boton = document.getElementById("btnPersonal");

        if (boton) {
            boton.classList.toggle(
                "d-none",
                !(typeof usuarioAdmin !== "undefined" && usuarioAdmin && usuarioAdmin.rol === "ADMIN")
            );
        }
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

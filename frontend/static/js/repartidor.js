/* ========================================================
   PANEL DEL REPARTIDOR
   Ve solo sus pedidos, abre la ruta, llama al cliente y
   marca la entrega. Se actualiza cada 30 segundos.
======================================================== */

const CLAVE_TOKEN = "kimbos_repartidor_token";

// La sesion se cierra sola tras este tiempo sin uso (tocar, escribir,
// desplazarse). La actualizacion automatica no cuenta como uso.
const MINUTOS_INACTIVIDAD = 10;
const CLAVE_ACTIVIDAD = "kimbos_repartidor_actividad";

let temporizador = null;
let vigilanteInactividad = null;


function registrarActividad() {

    if (token()) {
        localStorage.setItem(CLAVE_ACTIVIDAD, String(Date.now()));
    }
}


function sesionInactiva() {

    const ultima = Number(localStorage.getItem(CLAVE_ACTIVIDAD) || 0);

    // Sin registro = recien ingresado (aun no hubo tiempo de inactividad)
    if (!ultima) {
        return false;
    }

    return Date.now() - ultima > MINUTOS_INACTIVIDAD * 60000;
}


function vigilarInactividad() {

    clearInterval(vigilanteInactividad);

    vigilanteInactividad = setInterval(() => {

        if (token() && sesionInactiva()) {
            cerrarSesion(`Tu sesión se cerró por ${MINUTOS_INACTIVIDAD} minutos de inactividad. Vuelve a ingresar.`);
        }

    }, 15000);
}


function token() {
    return localStorage.getItem(CLAVE_TOKEN);
}


function escapar(valor) {

    return String(valor ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}


async function api(ruta, opciones = {}) {

    const respuesta = await fetch(ruta, {
        ...opciones,
        headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token()}`
        }
    });

    const datos = await respuesta.json();

    // Sesion vencida o cuenta sin permiso: volver al login
    if (respuesta.status === 401 || respuesta.status === 403) {
        cerrarSesion(datos.mensaje);
        throw new Error(datos.mensaje || "Sesión no válida");
    }

    if (!respuesta.ok || !datos.ok) {
        throw new Error(datos.mensaje || "Ocurrió un error");
    }

    return datos;
}


function mostrar(vista) {

    document.getElementById("vistaLogin").classList.toggle("d-none", vista !== "login");
    document.getElementById("vistaPanel").classList.toggle("d-none", vista !== "panel");
    document.getElementById("btnSalir").classList.toggle("d-none", vista !== "panel");
}


function cerrarSesion(mensaje) {

    localStorage.removeItem(CLAVE_TOKEN);
    localStorage.removeItem(CLAVE_ACTIVIDAD);
    clearInterval(temporizador);
    clearInterval(vigilanteInactividad);
    mostrar("login");

    if (mensaje) {
        const error = document.getElementById("errorLogin");
        error.textContent = mensaje;
        error.classList.remove("d-none");
    }
}


/* ================= LOGIN ================= */

async function iniciarSesion(evento) {

    evento.preventDefault();

    const error = document.getElementById("errorLogin");
    error.classList.add("d-none");

    try {

        const respuesta = await fetch("/api/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                correo: document.getElementById("correo").value.trim(),
                password: document.getElementById("password").value
            })
        });

        const datos = await respuesta.json();

        if (!respuesta.ok || !datos.ok) {
            throw new Error(datos.mensaje || "Datos incorrectos");
        }

        if (datos.usuario.rol !== "REPARTIDOR") {
            throw new Error("Esta cuenta no es de repartidor.");
        }

        localStorage.setItem(CLAVE_TOKEN, datos.token);
        registrarActividad();
        document.getElementById("password").value = "";

        await entrarAlPanel();

    } catch (fallo) {
        error.textContent = fallo.message;
        error.classList.remove("d-none");
    }
}


/* ================= PANEL ================= */

async function cargarPerfil() {

    const { repartidor } = await api("/api/repartidor/perfil");

    document.getElementById("nombreRepartidor").textContent = repartidor.nombre;
    document.getElementById("datosRepartidor").textContent =
        `${repartidor.codigo} · ${repartidor.tipo_vehiculo.toLowerCase()}`;
    document.getElementById("switchTurno").checked = repartidor.en_turno;
    document.getElementById("numEntregadosHoy").textContent = repartidor.entregas_hoy;
    document.getElementById("numATiempoHoy").textContent = repartidor.a_tiempo_hoy;
}


function etiquetaTiempo(pedido) {

    const restantes = pedido.minutos_restantes;

    if (restantes === null || restantes === undefined) {
        return "";
    }

    // En ruta: llegada estimada (ruta menos lo que ya lleva en camino).
    // "Quedan" es el plazo prometido al cliente, que puede ser mayor.
    const llegada = pedido.estado?.codigo === "EN_RUTA" && pedido.ruta_min !== null && pedido.ruta_min !== undefined
        ? `<span class="rep-tiempo rep-tiempo-ok">🛵 Llegas en ~${Math.max(pedido.ruta_min - (pedido.minutos_en_ruta || 0), 0)} min</span> `
        : "";

    if (restantes > 5) {
        return `${llegada}<span class="rep-tiempo rep-tiempo-ok">⏱️ Plazo: quedan ${restantes} min</span>`;
    }

    if (restantes >= 0) {
        return `${llegada}<span class="rep-tiempo rep-tiempo-justo">⚠️ Plazo: quedan ${restantes} min</span>`;
    }

    return `${llegada}<span class="rep-tiempo rep-tiempo-tarde">⛔ ${Math.abs(restantes)} min tarde</span>`;
}


function tarjetaPedido(pedido) {

    const destino = pedido.latitud !== null && pedido.longitud !== null
        ? `${pedido.latitud},${pedido.longitud}`
        : encodeURIComponent(pedido.direccion || "");

    const mapa = `https://www.google.com/maps/dir/?api=1&destination=${destino}&travelmode=driving`;

    const metodo = (pedido.metodo_pago || "").toUpperCase();
    const nombreMetodo = { YAPE: "Yape", PLIN: "Plin" }[metodo] || escapar(pedido.metodo_pago || "--");

    const cobrar = metodo === "EFECTIVO"
        ? `💵 Cobrar <strong>S/ ${pedido.total_soles.toFixed(2)}</strong> en efectivo`
        : pedido.pago_estado === "PAGADO"
        ? `✅ Ya pagó con ${nombreMetodo}: <strong>no cobrar</strong>`
        : `⚠️ Pago con ${nombreMetodo} sin confirmar · consulta con la tienda antes de entregar`;

    return `
        <article class="rep-pedido">

            <div class="rep-pedido-cab">
                <div>
                    <div class="rep-codigo">${escapar(pedido.codigo)}</div>
                    <div class="text-secondary small">
                        En ruta hace ${pedido.minutos_en_ruta} min ·
                        ${pedido.distancia_km ?? "--"} km · ruta ${pedido.ruta_min ?? "--"} min
                    </div>
                </div>
                ${etiquetaTiempo(pedido)}
            </div>

            <div class="rep-cliente">${escapar(pedido.cliente)}</div>
            <div class="rep-direccion">📍 ${escapar(pedido.direccion)}</div>

            ${pedido.indicaciones
                ? `<div class="rep-indicaciones">📝 ${escapar(pedido.indicaciones)}</div>`
                : ""}

            <div class="rep-dato">🧾 ${escapar(pedido.productos || "--")}</div>
            <div class="rep-cobro">${cobrar}</div>

            <div class="rep-acciones">
                <a class="btn btn-outline-dark rep-mapa" href="${mapa}" target="_blank" rel="noopener">
                    📍 Abrir en Maps
                </a>
                <button
                    class="btn btn-success rep-entregar"
                    onclick="marcarEntregado(${pedido.id}, '${escapar(pedido.codigo)}', this)"
                >
                    ✅ Marcar entregado
                </button>
            </div>

        </article>
    `;
}


async function cargarPedidos() {

    const datos = await api("/api/repartidor/pedidos");

    document.getElementById("numEnCurso").textContent = datos.en_curso.length;

    document.getElementById("listaEnCurso").innerHTML = datos.en_curso.length
        ? datos.en_curso.map(tarjetaPedido).join("")
        : `<div class="rep-vacio">No tienes pedidos por entregar. 🙌</div>`;

    document.getElementById("listaEntregados").innerHTML = datos.entregados_hoy.length
        ? datos.entregados_hoy.map((p) => `
            <div class="rep-entregado">
                <div>
                    <strong>${escapar(p.codigo)}</strong><br>
                    <span class="text-secondary">${escapar(p.cliente)}</span>
                </div>
                <div class="text-end">
                    ${p.con_retraso ? "⛔ Con retraso" : "✅ A tiempo"}<br>
                    <span class="text-secondary">${p.duracion_real_min ?? "--"} min</span>
                </div>
            </div>
        `).join("")
        : `<div class="rep-vacio">Aún no hay entregas hoy.</div>`;
}


async function actualizar() {

    try {
        await Promise.all([cargarPerfil(), cargarPedidos()]);
    } catch (error) {
        console.error(error);
    }
}


// Evita superponer actualizaciones si una tarda mas de 5 s
let actualizando = false;

async function actualizarSiLibre() {

    if (actualizando || document.visibilityState !== "visible") {
        return;
    }

    actualizando = true;

    try {
        await actualizar();
    } finally {
        actualizando = false;
    }
}


async function entrarAlPanel() {

    mostrar("panel");
    vigilarInactividad();
    await actualizar();

    clearInterval(temporizador);
    temporizador = setInterval(actualizarSiLibre, 5000);
}


async function marcarEntregado(pedidoId, codigo, boton) {

    if (!confirm(`¿Confirmas que entregaste el pedido ${codigo}?`)) {
        return;
    }

    boton.disabled = true;
    boton.textContent = "Guardando…";

    try {
        await api(`/api/repartidor/pedidos/${pedidoId}/entregado`, { method: "POST" });
        await actualizar();
    } catch (error) {
        alert(error.message);
        boton.disabled = false;
        boton.textContent = "✅ Marcar entregado";
    }
}


async function cambiarTurno(evento) {

    const interruptor = evento.target;

    try {
        await api("/api/repartidor/turno", {
            method: "PATCH",
            body: JSON.stringify({ en_turno: interruptor.checked })
        });
    } catch (error) {
        interruptor.checked = !interruptor.checked;
        alert(error.message);
    }
}


document.addEventListener("DOMContentLoaded", () => {

    document.getElementById("formLogin").addEventListener("submit", iniciarSesion);
    // Cerrar sesion a mano: vuelve a la pagina principal de la tienda
    document.getElementById("btnSalir").addEventListener("click", () => {
        localStorage.removeItem(CLAVE_TOKEN);
        localStorage.removeItem(CLAVE_ACTIVIDAD);
        clearInterval(temporizador);
        clearInterval(vigilanteInactividad);
        window.location.href = "/";
    });

    // Uso real de la persona (no la actualizacion automatica)
    ["click", "keydown", "touchstart", "scroll"].forEach((tipo) => {
        document.addEventListener(tipo, registrarActividad, { passive: true });
    });

    // Al volver a la pestana (celular desbloqueado): revisar en el acto
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible" && token() && sesionInactiva()) {
            cerrarSesion(`Tu sesión se cerró por ${MINUTOS_INACTIVIDAD} minutos de inactividad. Vuelve a ingresar.`);
        }
    });
    document.getElementById("switchTurno").addEventListener("change", cambiarTurno);
    document.getElementById("btnActualizar").addEventListener("click", (evento) => {
        evento.preventDefault();
        actualizar();
    });

    if (token() && sesionInactiva()) {
        // Se dejo abierta y paso el tiempo sin uso
        cerrarSesion(`Tu sesión se cerró por ${MINUTOS_INACTIVIDAD} minutos de inactividad. Vuelve a ingresar.`);
    } else if (token()) {
        registrarActividad();
        entrarAlPanel();
    } else {
        mostrar("login");
    }
});



/* ================= CAMBIAR MI CONTRASEÑA ================= */

document.addEventListener("DOMContentLoaded", () => {

    const formulario = document.getElementById("formMiPassword");

    if (!formulario) {
        return;
    }

    formulario.addEventListener("submit", async (evento) => {

        evento.preventDefault();

        const mensaje = document.getElementById("mensajeMiPassword");

        if (formulario.nueva.value !== formulario.confirmar.value) {
            mensaje.className = "alert alert-warning py-2";
            mensaje.textContent = "La confirmación no coincide con la nueva contraseña.";
            return;
        }

        try {

            const datos = await api("/api/auth/cambiar-password", {
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
    });
});

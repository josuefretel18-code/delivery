/* ========================================================
   ASISTENTE CON LLM (tienda y panel admin)

   Configuracion en el HTML:
   <div id="kimbosAsistente"
        data-endpoint="/api/asistente/cliente"
        data-token="kimbos_token"
        data-titulo="Asistente Kimbos"
        data-sugerencias="Pregunta 1|Pregunta 2"></div>
======================================================== */

(function () {

    const raiz = document.getElementById("kimbosAsistente");

    if (!raiz) {
        return;
    }

    const config = {
        endpoint: raiz.dataset.endpoint,
        claveToken: raiz.dataset.token,
        titulo: raiz.dataset.titulo || "Asistente",
        bienvenida: raiz.dataset.bienvenida || "¡Hola! ¿En qué te ayudo?",
        sugerencias: (raiz.dataset.sugerencias || "")
            .split("|")
            .filter(Boolean)
    };

    // Solo los ultimos mensajes viajan al servidor (menos tokens).
    const historial = [];
    const MAX_HISTORIAL = 6;

    let enviando = false;
    let estadoCargado = false;

    raiz.innerHTML = `
        <button class="asis-boton" type="button" aria-label="Abrir asistente">
            💬 Asistente
        </button>

        <section class="asis-panel" aria-label="${config.titulo}">
            <div class="asis-cabecera">
                <div>
                    <strong></strong>
                    <small>Con IA · respuestas breves</small>
                </div>
                <button class="asis-cerrar" type="button" aria-label="Cerrar">×</button>
            </div>

            <div class="asis-mensajes"></div>

            <div class="asis-sugerencias"></div>

            <form class="asis-form">
                <input type="text" maxlength="500" placeholder="Escribe tu pregunta..." autocomplete="off">
                <button type="submit">Enviar</button>
            </form>

            <div class="asis-pie"></div>
        </section>
    `;

    const boton = raiz.querySelector(".asis-boton");
    const panel = raiz.querySelector(".asis-panel");
    const mensajes = raiz.querySelector(".asis-mensajes");
    const sugerencias = raiz.querySelector(".asis-sugerencias");
    const formulario = raiz.querySelector(".asis-form");
    const entrada = formulario.querySelector("input");
    const botonEnviar = formulario.querySelector("button");
    const pie = raiz.querySelector(".asis-pie");

    raiz.querySelector(".asis-cabecera strong").textContent = config.titulo;


    function token() {
        return localStorage.getItem(config.claveToken);
    }


    function agregarMensaje(rol, texto) {

        const burbuja = document.createElement("div");

        burbuja.className = `asis-msg ${rol}`;

        // Texto plano (sin HTML): se quitan las marcas de negrita.
        burbuja.textContent = texto.replace(/\*\*/g, "");

        mensajes.appendChild(burbuja);
        mensajes.scrollTop = mensajes.scrollHeight;

        return burbuja;
    }


    function mostrarSugerencias() {

        sugerencias.innerHTML = "";

        if (historial.length) {
            return;
        }

        config.sugerencias.forEach((texto) => {

            const chip = document.createElement("button");

            chip.type = "button";
            chip.textContent = texto;
            chip.addEventListener("click", () => enviar(texto));

            sugerencias.appendChild(chip);
        });
    }


    function actualizarPie(restantes) {

        pie.textContent = Number.isInteger(restantes)
            ? `Te quedan ${restantes} mensajes hoy.`
            : "";
    }


    async function cargarEstado() {

        try {

            const respuesta = await fetch("/api/asistente/estado", {
                headers: { "Authorization": `Bearer ${token()}` }
            });

            const datos = await respuesta.json();

            if (!respuesta.ok) {
                return;
            }

            estadoCargado = true;

            if (!datos.activo) {
                agregarMensaje("aviso", datos.motivo || "El asistente no está disponible.");
                botonEnviar.disabled = true;
            }

            actualizarPie(datos.restantes_hoy);

        } catch (error) {
            console.error(error);
        }
    }


    async function enviar(texto) {

        texto = (texto || "").trim();

        if (!texto || enviando) {
            return;
        }

        if (!token()) {
            agregarMensaje("aviso", "Inicia sesión para usar el asistente.");
            return;
        }

        enviando = true;
        botonEnviar.disabled = true;
        entrada.value = "";

        agregarMensaje("user", texto);
        sugerencias.innerHTML = "";

        const escribiendo = agregarMensaje("assistant", "Escribiendo…");

        try {

            const respuesta = await fetch(config.endpoint, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${token()}`
                },
                body: JSON.stringify({
                    mensaje: texto,
                    historial: historial.slice(-MAX_HISTORIAL)
                })
            });

            const datos = await respuesta.json();

            escribiendo.remove();

            if (!respuesta.ok || !datos.ok) {
                agregarMensaje("aviso", datos.mensaje || "No se pudo responder.");
                return;
            }

            agregarMensaje("assistant", datos.respuesta);

            historial.push(
                { rol: "user", texto: texto },
                { rol: "assistant", texto: datos.respuesta }
            );

            actualizarPie(datos.restantes_hoy);

            if (datos.restantes_hoy === 0) {
                agregarMensaje("aviso", "Alcanzaste el límite de mensajes por hoy.");
                return;
            }

        } catch (error) {

            escribiendo.remove();
            agregarMensaje("aviso", "Error de conexión con el asistente.");

        } finally {

            enviando = false;

            if (pie.textContent !== "Te quedan 0 mensajes hoy.") {
                botonEnviar.disabled = false;
                entrada.focus();
            }
        }
    }


    boton.addEventListener("click", () => {

        panel.classList.toggle("abierto");

        if (!panel.classList.contains("abierto")) {
            return;
        }

        if (!mensajes.childElementCount) {
            agregarMensaje("assistant", config.bienvenida);
            mostrarSugerencias();
        }

        if (!token()) {
            if (!mensajes.querySelector(".aviso")) {
                agregarMensaje("aviso", "Inicia sesión para usar el asistente.");
            }
            return;
        }

        if (!estadoCargado) {
            cargarEstado();
        }

        entrada.focus();
    });

    raiz.querySelector(".asis-cerrar").addEventListener("click", () => {
        panel.classList.remove("abierto");
    });

    formulario.addEventListener("submit", (evento) => {
        evento.preventDefault();
        enviar(entrada.value);
    });

})();

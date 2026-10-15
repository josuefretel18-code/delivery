/* ========================================================
   RESPUESTAS DEL SERVIDOR
   1. Reintento automatico: si el servidor no responde por un
      momento (se esta reiniciando o desplegando, o el internet
      se corto), las consultas se repiten solas antes de fallar.
   2. Si aun asi llega una pagina HTML en vez de JSON, se muestra
      un mensaje entendible en lugar de
      "Unexpected token '<' ... is not valid JSON".
======================================================== */

(function () {

    // Esperas entre intentos (ms): 3 intentos mas en ~10 segundos
    const ESPERAS = [1500, 3000, 5000];

    // Codigos de "servidor no disponible por un momento"
    const PASAJEROS = [502, 503, 504];

    const fetchOriginal = window.fetch.bind(window);

    function esperar(ms) {
        return new Promise((listo) => setTimeout(listo, ms));
    }

    function sePuedeRepetir(recurso, opciones) {

        const metodo = String(
            (opciones && opciones.method) ||
            (recurso instanceof Request ? recurso.method : "GET")
        ).toUpperCase();

        const url = String(recurso instanceof Request ? recurso.url : recurso);

        // Solo consultas (no crean ni cambian nada) y el inicio de sesion.
        // Crear un pedido o marcarlo entregado NO se repite: podria
        // duplicarse si el primer intento si llego al servidor.
        return (
            metodo === "GET" ||
            metodo === "HEAD" ||
            url.includes("/api/auth/login")
        );
    }

    function esHtml(respuesta) {
        return (respuesta.headers.get("content-type") || "").includes("text/html");
    }

    window.fetch = async function (recurso, opciones) {

        if (!sePuedeRepetir(recurso, opciones)) {
            return fetchOriginal(recurso, opciones);
        }

        for (let intento = 0; ; intento++) {

            const ultimo = intento >= ESPERAS.length;

            try {

                const respuesta = await fetchOriginal(recurso, opciones);

                const url = String(recurso instanceof Request ? recurso.url : recurso);
                const pasajero =
                    PASAJEROS.includes(respuesta.status) ||
                    (url.includes("/api/") && esHtml(respuesta));

                if (!pasajero || ultimo) {
                    return respuesta;
                }

            } catch (error) {

                // Sin conexion: se reintenta, salvo que se haya cancelado
                if (ultimo || (error && error.name === "AbortError")) {
                    throw error;
                }
            }

            await esperar(ESPERAS[intento]);
        }
    };


    const jsonOriginal = Response.prototype.json;

    Response.prototype.json = async function () {

        try {
            return await jsonOriginal.call(this);
        } catch (error) {

            if (error instanceof SyntaxError) {
                throw new Error(
                    "El servidor no respondió correctamente. " +
                    "Espera unos segundos e intenta de nuevo."
                );
            }

            throw error;
        }
    };

})();

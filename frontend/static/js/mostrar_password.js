/* ========================================================
   MOSTRAR / OCULTAR CONTRASEÑA
   Agrega un botón con un ojo a cada casilla de contraseña
   de la página (tienda, admin, repartidor y acceso).
======================================================== */

(function () {

    const OJO = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"></path>
            <circle cx="12" cy="12" r="3"></circle>
        </svg>`;

    const OJO_TACHADO = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M17.94 17.94A10.4 10.4 0 0 1 12 19c-6.5 0-10-7-10-7a18.6 18.6 0 0 1 5.06-5.94"></path>
            <path d="M9.9 4.24A9.5 9.5 0 0 1 12 4c6.5 0 10 7 10 7a18.7 18.7 0 0 1-2.16 3.19"></path>
            <path d="M14.12 14.12a3 3 0 1 1-4.24-4.24"></path>
            <line x1="2" y1="2" x2="22" y2="22"></line>
        </svg>`;

    const estilo = document.createElement("style");
    estilo.textContent = `
        .password-con-ojo { position: relative; display: block; }
        .password-con-ojo > input { padding-right: 44px; }
        .boton-ojo {
            position: absolute; top: 50%; right: 6px; transform: translateY(-50%);
            width: 34px; height: 34px; border: 0; border-radius: 8px;
            background: transparent; color: #6c757d;
            display: inline-flex; align-items: center; justify-content: center;
            cursor: pointer;
        }
        .boton-ojo:hover { color: #171717; background: rgba(0, 0, 0, 0.05); }
        .boton-ojo:focus-visible { outline: 2px solid #ff6b00; outline-offset: 1px; }
    `;
    document.head.appendChild(estilo);


    function agregarOjo(input) {

        if (input.dataset.conOjo) {
            return;
        }

        input.dataset.conOjo = "1";

        const contenedor = document.createElement("span");
        contenedor.className = "password-con-ojo";

        // Los margenes del campo pasan al contenedor para que el ojo
        // quede centrado verticalmente.
        [...input.classList]
            .filter((clase) => /^m[tbsexy]?-/.test(clase))
            .forEach((clase) => {
                input.classList.remove(clase);
                contenedor.classList.add(clase);
            });

        input.parentNode.insertBefore(contenedor, input);
        contenedor.appendChild(input);

        const boton = document.createElement("button");
        boton.type = "button";
        boton.className = "boton-ojo";
        boton.innerHTML = OJO;
        boton.setAttribute("aria-label", "Mostrar contraseña");
        boton.title = "Mostrar contraseña";

        boton.addEventListener("click", () => {

            const visible = input.type === "text";

            input.type = visible ? "password" : "text";
            boton.innerHTML = visible ? OJO : OJO_TACHADO;
            boton.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
            boton.title = visible ? "Mostrar contraseña" : "Ocultar contraseña";

            input.focus();
        });

        contenedor.appendChild(boton);

        // Al enviar el formulario, la contraseña vuelve a ocultarse
        const formulario = input.closest("form");

        if (formulario) {
            formulario.addEventListener("submit", () => {
                input.type = "password";
                boton.innerHTML = OJO;
                boton.setAttribute("aria-label", "Mostrar contraseña");
            });
        }
    }


    function revisar() {
        document.querySelectorAll('input[type="password"]').forEach(agregarOjo);
    }


    document.addEventListener("DOMContentLoaded", revisar);

    // Por si alguna página agrega casillas después de cargar
    new MutationObserver(revisar).observe(document.documentElement, {
        childList: true,
        subtree: true
    });

})();

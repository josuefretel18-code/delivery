let catalogoCompleto = [];
let carrito = [];
let usuarioActual = null;
let sedeActual = null;

let mapaEntrega = null;
let marcadorOrigen = null;
let marcadorDestino = null;

let autocompleteDestino = null;

let destinoEntrega = null;

let googleMapsListo = false;

let rutaEntrega = null;

let polilineasRuta = [];

let datosRuta = {
    distancia_km: null,
    duracion_estimada_min: null,
    costo_delivery: null
};

/* ========================================================
   INICIO
======================================================== */

document.addEventListener("DOMContentLoaded", () => {

    cargarSede();
    cargarCatalogo();

    verificarSesionGuardada();
    configurarAutenticacion();
    configurarContinuarPedido();
    configurarResumenPedido();
    configurarMisPedidos();

});


/* ========================================================
   SEDE
======================================================== */

async function cargarSede() {

    try {

        const respuesta = await fetch(
            "/api/sedes/activa"
        );

        const datos = await respuesta.json();

        if (!datos.ok) {
            return;
        }
        sedeActual = datos.sede;

        document.getElementById(
            "nombreNegocio"
        ).textContent =
            `${datos.sede.negocio} - ${datos.sede.nombre}`;

        document.getElementById(
            "direccionSede"
        ).textContent =
            datos.sede.direccion;

    } catch (error) {

        console.error(
            "Error cargando sede:",
            error
        );

    }

}


/* ========================================================
   CATÁLOGO
======================================================== */

async function cargarCatalogo() {

    const contenedor =
        document.getElementById(
            "productos"
        );

    try {

        const respuesta = await fetch(
            "/api/catalogo"
        );

        const datos = await respuesta.json();

        if (!datos.ok) {
            throw new Error(
                "No se pudo cargar el catálogo"
            );
        }

        catalogoCompleto =
            datos.categorias;

        renderizarCategorias();
        renderizarProductos();

    } catch (error) {

        contenedor.innerHTML = `
            <div class="col-12">
                <div class="alert alert-danger">
                    No se pudo cargar el menú.
                </div>
            </div>
        `;

        console.error(error);

    }

}


/* ========================================================
   CATEGORÍAS
======================================================== */

function renderizarCategorias() {

    const contenedor =
        document.getElementById(
            "categorias"
        );

    contenedor.innerHTML = `
        <button
            class="btn-categoria activa"
            onclick="filtrarCategoria(null, this)"
        >
            Todos
        </button>
    `;

    catalogoCompleto.forEach(
        categoria => {

            contenedor.innerHTML += `
                <button
                    class="btn-categoria"
                    onclick="filtrarCategoria(
                        ${categoria.id},
                        this
                    )"
                >
                    ${escaparHtml(
                        categoria.nombre
                    )}
                </button>
            `;

        }
    );

}


function filtrarCategoria(
    categoriaId,
    boton
) {

    document
        .querySelectorAll(
            ".btn-categoria"
        )
        .forEach(
            elemento =>
                elemento.classList.remove(
                    "activa"
                )
        );

    boton.classList.add(
        "activa"
    );

    renderizarProductos(
        categoriaId
    );

}


/* ========================================================
   PRODUCTOS
======================================================== */

function renderizarProductos(
    categoriaId = null
) {

    const contenedor =
        document.getElementById(
            "productos"
        );

    let productos = [];

    catalogoCompleto.forEach(
        categoria => {

            if (
                categoriaId === null ||
                categoria.id === categoriaId
            ) {

                categoria.productos.forEach(
                    producto => {

                        productos.push({
                            ...producto,
                            categoria:
                                categoria.nombre
                        });

                    }
                );

            }

        }
    );

    if (productos.length === 0) {

        contenedor.innerHTML = `
            <div class="col-12 text-center py-5">
                <h5>
                    No hay productos disponibles
                    en esta categoría.
                </h5>
            </div>
        `;

        return;
    }

    contenedor.innerHTML = "";

    productos.forEach(
        producto => {

            const imagen = producto.imagen_url
                ? `
                    <img
                        src="${producto.imagen_url}"
                        alt="${escaparHtml(
                            producto.nombre
                        )}"
                    >
                `
                : `
                    <div class="producto-placeholder">
                        🍔
                    </div>
                `;

            const boton = producto.disponible
                ? `
                    <button
                        class="btn btn-agregar w-100"
                        onclick="agregarAlCarrito(
                            ${producto.id}
                        )"
                    >
                        + Agregar
                    </button>
                `
                : `
                    <button
                        class="btn btn-agotado w-100"
                        disabled
                    >
                        Agotado
                    </button>
                `;

            contenedor.innerHTML += `
                <div
                    class="
                        col-12
                        col-sm-6
                        col-lg-4
                    "
                >

                    <div class="producto-card">

                        <div class="producto-imagen">
                            ${imagen}
                        </div>

                        <div class="producto-body">

                            <small
                                class="text-secondary"
                            >
                                ${escaparHtml(
                                    producto.categoria
                                )}
                            </small>

                            <h5 class="producto-nombre mt-1">
                                ${escaparHtml(
                                    producto.nombre
                                )}
                            </h5>

                            <p class="producto-descripcion">
                                ${escaparHtml(
                                    producto.descripcion ||
                                    "Producto Kimbos"
                                )}
                            </p>

                            <div
                                class="
                                    d-flex
                                    justify-content-between
                                    align-items-center
                                    mb-3
                                "
                            >

                                <span class="producto-precio">
                                    S/
                                    ${Number(
                                        producto.precio
                                    ).toFixed(2)}
                                </span>

                                <span class="producto-tiempo">
                                    ⏱
                                    ${producto.tiempo_preparacion_min}
                                    min
                                </span>

                            </div>

                            ${boton}

                        </div>

                    </div>

                </div>
            `;

        }
    );

}


/* ========================================================
   CARRITO
======================================================== */

function buscarProducto(
    productoId
) {

    for (
        const categoria
        of catalogoCompleto
    ) {

        const producto =
            categoria.productos.find(
                p => p.id === productoId
            );

        if (producto) {
            return producto;
        }

    }

    return null;

}


function agregarAlCarrito(
    productoId
) {

    const producto =
        buscarProducto(
            productoId
        );

    if (
        !producto ||
        !producto.disponible
    ) {
        return;
    }

    const existente =
        carrito.find(
            item =>
                item.id === productoId
        );

    if (existente) {

        existente.cantidad += 1;

    } else {

        carrito.push({
            id: producto.id,
            nombre: producto.nombre,
            precio: Number(
                producto.precio
            ),
            cantidad: 1,
            tiempo_preparacion_min:
                producto.tiempo_preparacion_min
        });

    }

    actualizarCarrito();

}


function cambiarCantidad(
    productoId,
    cambio
) {

    const item =
        carrito.find(
            producto =>
                producto.id === productoId
        );

    if (!item) {
        return;
    }

    item.cantidad += cambio;

    if (item.cantidad <= 0) {

        carrito =
            carrito.filter(
                producto =>
                    producto.id !== productoId
            );

    }

    actualizarCarrito();

}


function actualizarCarrito() {

    const lista =
        document.getElementById(
            "listaCarrito"
        );

    const vacio =
        document.getElementById(
            "carritoVacio"
        );

    const resumen =
        document.getElementById(
            "resumenCarrito"
        );

    const contador =
        document.getElementById(
            "contadorCarrito"
        );

    const cantidadProductos =
        carrito.reduce(
            (total, item) =>
                total + item.cantidad,
            0
        );

    const subtotal =
        carrito.reduce(
            (total, item) =>
                total +
                (
                    item.precio *
                    item.cantidad
                ),
            0
        );

    contador.textContent =
        cantidadProductos;

    document.getElementById(
        "cantidadProductos"
    ).textContent =
        cantidadProductos;

    document.getElementById(
        "subtotalCarrito"
    ).textContent =
        `S/ ${subtotal.toFixed(2)}`;

    if (carrito.length === 0) {

        lista.innerHTML = "";

        vacio.classList.remove(
            "d-none"
        );

        resumen.classList.add(
            "d-none"
        );

        return;

    }

    vacio.classList.add(
        "d-none"
    );

    resumen.classList.remove(
        "d-none"
    );

    lista.innerHTML = "";

    carrito.forEach(
        item => {

            lista.innerHTML += `
                <div class="item-carrito">

                    <div
                        class="
                            d-flex
                            justify-content-between
                            gap-3
                        "
                    >

                        <div>

                            <h6>
                                ${escaparHtml(
                                    item.nombre
                                )}
                            </h6>

                            <small class="text-secondary">
                                S/
                                ${item.precio.toFixed(2)}
                                c/u
                            </small>

                        </div>

                        <strong>
                            S/
                            ${(
                                item.precio *
                                item.cantidad
                            ).toFixed(2)}
                        </strong>

                    </div>

                    <div
                        class="
                            controles-cantidad
                            mt-3
                        "
                    >

                        <button
                            class="btn-cantidad"
                            onclick="
                                cambiarCantidad(
                                    ${item.id},
                                    -1
                                )
                            "
                        >
                            −
                        </button>

                        <strong>
                            ${item.cantidad}
                        </strong>

                        <button
                            class="btn-cantidad"
                            onclick="
                                cambiarCantidad(
                                    ${item.id},
                                    1
                                )
                            "
                        >
                            +
                        </button>

                    </div>

                </div>
            `;

        }
    );

}


/* ========================================================
   SEGURIDAD DE TEXTO
======================================================== */

function escaparHtml(
    texto
) {

    const div =
        document.createElement(
            "div"
        );

    div.textContent =
        texto ?? "";

    return div.innerHTML;

}
/* ========================================================
   AUTENTICACIÓN
======================================================== */

function configurarAutenticacion() {

    const formLogin =
        document.getElementById(
            "formLogin"
        );

    const formRegistro =
        document.getElementById(
            "formRegistro"
        );

    formLogin.addEventListener(
        "submit",
        iniciarSesion
    );

    formRegistro.addEventListener(
        "submit",
        registrarCliente
    );

}


/* ========================================================
   LOGIN
======================================================== */

async function iniciarSesion(
    event
) {

    event.preventDefault();

    const correo =
        document.getElementById(
            "loginCorreo"
        ).value.trim();

    const password =
        document.getElementById(
            "loginPassword"
        ).value;

    const mensaje =
        document.getElementById(
            "mensajeLogin"
        );

    mensaje.classList.add(
        "d-none"
    );

    try {

        const respuesta = await fetch(
            "/api/auth/login",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    correo,
                    password
                })
            }
        );

        const datos =
            await respuesta.json();

        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            mostrarMensaje(
                mensaje,
                datos.mensaje ||
                "Correo o contraseña incorrectos.",
                false
            );

            return;
        }

        localStorage.setItem(
            "kimbos_token",
            datos.token
        );

        await cargarPerfil();

        actualizarInterfazUsuario();

        cerrarModalAcceso();

        continuarDespuesDeLogin();

    } catch (error) {

        mostrarMensaje(
            mensaje,
            "No se pudo conectar con el servidor.",
            false
        );

        console.error(error);

    }

}


/* ========================================================
   REGISTRO
======================================================== */

async function registrarCliente(
    event
) {

    event.preventDefault();

    const nombre_completo =
        document.getElementById(
            "registroNombre"
        ).value.trim();

    const correo =
        document.getElementById(
            "registroCorreo"
        ).value.trim();

    const telefono =
        document.getElementById(
            "registroTelefono"
        ).value.trim();

    const password =
        document.getElementById(
            "registroPassword"
        ).value;

    const mensaje =
        document.getElementById(
            "mensajeRegistro"
        );

    mensaje.classList.add(
        "d-none"
    );

    if (
        password.length < 8
    ) {

        mostrarMensaje(
            mensaje,
            "La contraseña debe tener al menos 8 caracteres.",
            false
        );

        return;
    }

    try {

        const respuesta = await fetch(
            "/api/auth/registro",
            {
                method: "POST",

                headers: {
                    "Content-Type":
                        "application/json"
                },

                body: JSON.stringify({
                    nombre_completo,
                    correo,
                    telefono,
                    password
                })
            }
        );

        const datos =
            await respuesta.json();

        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            mostrarMensaje(
                mensaje,
                datos.mensaje ||
                "No se pudo crear la cuenta.",
                false
            );

            return;
        }

        mostrarMensaje(
            mensaje,
            "Cuenta creada correctamente. Ahora inicia sesión.",
            true
        );

        document.getElementById(
            "loginCorreo"
        ).value =
            correo;

        document.getElementById(
            "loginPassword"
        ).value =
            "";

        setTimeout(() => {

            const botonLogin =
                document.querySelector(
                    '[data-bs-target="#panelLogin"]'
                );

            bootstrap.Tab
                .getOrCreateInstance(
                    botonLogin
                )
                .show();

        }, 700);

    } catch (error) {

        mostrarMensaje(
            mensaje,
            "No se pudo conectar con el servidor.",
            false
        );

        console.error(error);

    }

}


/* ========================================================
   PERFIL
======================================================== */

async function cargarPerfil() {

    const token =
        localStorage.getItem(
            "kimbos_token"
        );

    if (!token) {
        usuarioActual = null;
        return false;
    }

    try {

        const respuesta = await fetch(
            "/api/auth/me",
            {
                headers: {
                    "Authorization":
                        `Bearer ${token}`
                }
            }
        );

        if (!respuesta.ok) {

            localStorage.removeItem(
                "kimbos_token"
            );

            usuarioActual = null;

            return false;
        }

        const datos =
            await respuesta.json();

        usuarioActual =
            datos.usuario || datos;

        return true;

    } catch (error) {

        console.error(
            "Error verificando sesión:",
            error
        );

        usuarioActual = null;

        return false;

    }

}


async function verificarSesionGuardada() {

    await cargarPerfil();

    actualizarInterfazUsuario();

}


/* ========================================================
   INTERFAZ DEL USUARIO
======================================================== */

function actualizarInterfazUsuario() {

    const boton =
        document.getElementById(
            "btnCuenta"
        );

    const botonPedidos =
        document.getElementById(
            "btnMisPedidos"
        );


    if (!usuarioActual) {

        boton.textContent =
            "👤 Ingresar";

        boton.setAttribute(
            "data-bs-toggle",
            "modal"
        );

        boton.setAttribute(
            "data-bs-target",
            "#modalAcceso"
        );

        botonPedidos.classList.add(
            "d-none"
        );

        return;
    }


    const nombre =
        usuarioActual.nombre ||
        usuarioActual.nombre_completo ||
        "Mi cuenta";


    boton.textContent =
        `👤 ${nombre.split(" ")[0]}`;


    boton.removeAttribute(
        "data-bs-toggle"
    );

    boton.removeAttribute(
        "data-bs-target"
    );


    botonPedidos.classList.remove(
        "d-none"
    );

}


/* ========================================================
   CONTINUAR PEDIDO
======================================================== */

function configurarContinuarPedido() {

    const boton =
        document.getElementById(
            "btnContinuarPedido"
        );

    boton.addEventListener(
        "click",
        async () => {

            if (
                carrito.length === 0
            ) {
                return;
            }

            const sesionValida =
                await cargarPerfil();

            if (!sesionValida) {

                abrirModalAcceso();

                return;
            }

            continuarDespuesDeLogin();

        }
    );

}


function continuarDespuesDeLogin() {

    if (
        !usuarioActual ||
        carrito.length === 0
    ) {
        return;
    }

    const panelCarrito =
        document.getElementById(
            "carritoPanel"
        );

    const offcanvas =
        bootstrap.Offcanvas.getInstance(
            panelCarrito
        );

    if (offcanvas) {
        offcanvas.hide();
    }

    setTimeout(() => {

        const modalElemento =
            document.getElementById(
                "modalEntrega"
            );

        const modal =
            bootstrap.Modal.getOrCreateInstance(
                modalElemento
            );

        modal.show();

    }, 250);

}


/* ========================================================
   MODAL
======================================================== */

function abrirModalAcceso() {

    const modalElemento =
        document.getElementById(
            "modalAcceso"
        );

    const modal =
        bootstrap.Modal.getOrCreateInstance(
            modalElemento
        );

    modal.show();

}


function cerrarModalAcceso() {

    const modalElemento =
        document.getElementById(
            "modalAcceso"
        );

    const modal =
        bootstrap.Modal.getInstance(
            modalElemento
        );

    if (modal) {
        modal.hide();
    }

}


/* ========================================================
   MENSAJES
======================================================== */

function mostrarMensaje(
    elemento,
    texto,
    correcto
) {

    elemento.textContent =
        texto;

    elemento.className =
        correcto
            ? "alert alert-success"
            : "alert alert-danger";

}
/* ========================================================
   GOOGLE MAPS
======================================================== */

window.initGoogleMaps = async function () {

    googleMapsListo = true;

    const modalEntrega =
        document.getElementById(
            "modalEntrega"
        );

    modalEntrega.addEventListener(
        "shown.bs.modal",
        async () => {

            if (!mapaEntrega) {
                await inicializarMapaEntrega();
            }

        }
    );

};


async function inicializarMapaEntrega() {

    if (
        !googleMapsListo ||
        !sedeActual
    ) {
        return;
    }

    const { Map } =
        await google.maps.importLibrary(
            "maps"
        );

    const { AdvancedMarkerElement } =
        await google.maps.importLibrary(
            "marker"
        );

    const { PlaceAutocompleteElement } =
        await google.maps.importLibrary(
            "places"
        );


    const origen = {
        lat: Number(
            sedeActual.latitud
        ),

        lng: Number(
            sedeActual.longitud
        )
    };


    mapaEntrega = new Map(
        document.getElementById(
            "mapaEntrega"
        ),
        {
            center: origen,
            zoom: 15,
            mapId: "DEMO_MAP_ID",
            mapTypeControl: false,
            streetViewControl: false
        }
    );


    marcadorOrigen =
        new AdvancedMarkerElement({
            map: mapaEntrega,
            position: origen,
            title:
                `${sedeActual.negocio} - ${sedeActual.nombre}`
        });


    document.getElementById(
        "textoOrigenEntrega"
    ).textContent =
        `${sedeActual.negocio} - ${sedeActual.nombre}`;


    const contenedor =
        document.getElementById(
            "contenedorAutocomplete"
        );

    contenedor.innerHTML = "";


    autocompleteDestino =
        new PlaceAutocompleteElement();


    autocompleteDestino.placeholder =
        "Busca tu dirección";


    autocompleteDestino.includedRegionCodes =
        ["pe"];


    autocompleteDestino.locationBias = {
        radius: 50000,
        center: origen
    };


    contenedor.appendChild(
        autocompleteDestino
    );


    autocompleteDestino.addEventListener(
        "gmp-select",
        async ({
            placePrediction
        }) => {

            const place =
                placePrediction.toPlace();


            await place.fetchFields({
                fields: [
                    "displayName",
                    "formattedAddress",
                    "location"
                ]
            });


            if (!place.location) {
                return;
            }


            seleccionarDestino({
                lat:
                    place.location.lat(),

                lng:
                    place.location.lng(),

                direccion:
                    place.formattedAddress ||
                    place.displayName ||
                    "Destino seleccionado"
            });

        }
    );


    document.getElementById(
        "btnUbicacionActual"
    ).addEventListener(
        "click",
        usarUbicacionActual
    );

}
/* ========================================================
   SELECCIONAR DESTINO
======================================================== */

async function seleccionarDestino(
    destino
) {

    destinoEntrega = destino;


    const {
        AdvancedMarkerElement
    } =
        await google.maps.importLibrary(
            "marker"
        );


    if (marcadorDestino) {
        marcadorDestino.map = null;
    }


    marcadorDestino =
        new AdvancedMarkerElement({
            map: mapaEntrega,

            position: {
                lat: destino.lat,
                lng: destino.lng
            },

            title:
                "Dirección de entrega"
        });


    mapaEntrega.setCenter({
        lat: destino.lat,
        lng: destino.lng
    });

    mapaEntrega.setZoom(
        16
    );


    document.getElementById(
        "textoDireccionDestino"
    ).textContent =
        destino.direccion;


    document.getElementById(
        "destinoSeleccionado"
    ).classList.remove(
        "d-none"
    );


    document.getElementById(
        "btnDestinoListo"
    ).disabled =
        false;


    document.getElementById(
        "mensajeMapa"
    ).textContent =
        "Ubicación de entrega seleccionada correctamente.";
    await calcularRutaEntrega();

}
/* ========================================================
   UBICACIÓN ACTUAL
======================================================== */

function usarUbicacionActual() {

    const mensaje =
        document.getElementById(
            "mensajeMapa"
        );


    if (!navigator.geolocation) {

        mensaje.textContent =
            "Tu navegador no permite obtener la ubicación.";

        return;
    }


    mensaje.textContent =
        "Obteniendo tu ubicación...";


    navigator.geolocation.getCurrentPosition(

        position => {

            const lat =
                position.coords.latitude;

            const lng =
                position.coords.longitude;


            seleccionarDestino({
                lat,
                lng,

                direccion:
                    `Ubicación actual (${lat.toFixed(6)}, ${lng.toFixed(6)})`
            });

        },

        error => {

            mensaje.textContent =
                "No fue posible obtener tu ubicación. Puedes buscar la dirección manualmente.";

            console.error(
                error
            );

        },

        {
            enableHighAccuracy: true,
            timeout: 10000
        }

    );

}
/* ========================================================
   CALCULAR RUTA DE DELIVERY
======================================================== */

async function calcularRutaEntrega() {

    if (
        !sedeActual ||
        !destinoEntrega ||
        !mapaEntrega
    ) {
        return;
    }


    const mensaje =
        document.getElementById(
            "mensajeMapa"
        );


    const resumen =
        document.getElementById(
            "resumenRuta"
        );


    const boton =
        document.getElementById(
            "btnDestinoListo"
        );


    boton.disabled = true;

    mensaje.textContent =
        "Calculando la mejor ruta de entrega...";


    try {

        const {
            Route
        } =
            await google.maps.importLibrary(
                "routes"
            );


        const origen = {
            lat: Number(
                sedeActual.latitud
            ),

            lng: Number(
                sedeActual.longitud
            )
        };


        const destino = {
            lat: Number(
                destinoEntrega.lat
            ),

            lng: Number(
                destinoEntrega.lng
            )
        };


        const solicitud = {

            origin: origen,

            destination: destino,

            travelMode: "DRIVING",

            routingPreference:
                "TRAFFIC_AWARE",

            fields: [
                "path",
                "distanceMeters",
                "durationMillis"
            ]

        };


        const resultado =
            await Route.computeRoutes(
                solicitud
            );


        if (
            !resultado.routes ||
            resultado.routes.length === 0
        ) {

            throw new Error(
                "Google Maps no encontró una ruta"
            );

        }


        rutaEntrega =
            resultado.routes[0];


        /* ==========================================
           BORRAR RUTA ANTERIOR
        ========================================== */

        polilineasRuta.forEach(
            linea => {

                linea.setMap(
                    null
                );

            }
        );


        polilineasRuta = [];


        /* ==========================================
           DIBUJAR RUTA
        ========================================== */

        polilineasRuta =
            rutaEntrega.createPolylines();


        polilineasRuta.forEach(
            linea => {

                linea.setMap(
                    mapaEntrega
                );

            }
        );


        /* ==========================================
           DISTANCIA
        ========================================== */

        const metros =
            rutaEntrega.distanceMeters ||
            0;


        const distanciaKm =
            metros / 1000;


        /* ==========================================
           DURACIÓN
        ========================================== */

        const duracionMillis =
            rutaEntrega.durationMillis ||
            0;


        const duracionMin =
            Math.ceil(
                duracionMillis /
                60000
            );


        /* ==========================================
           COSTO DELIVERY
           
           Regla inicial configurable:
           S/ 3.00 base
           + S/ 1.20 por km
        ========================================== */

        const costoBase =
            3.00;


        const costoPorKm =
            1.20;


        const costoDelivery =
            costoBase +
            (
                distanciaKm *
                costoPorKm
            );


        datosRuta = {

            distancia_km:
                Number(
                    distanciaKm.toFixed(2)
                ),

            duracion_estimada_min:
                duracionMin,

            costo_delivery:
                Number(
                    costoDelivery.toFixed(2)
                )

        };


        /* ==========================================
           MOSTRAR RESULTADOS
        ========================================== */

        document.getElementById(
            "rutaDistancia"
        ).textContent =
            `${datosRuta.distancia_km} km`;


        document.getElementById(
            "rutaTiempo"
        ).textContent =
            `${datosRuta.duracion_estimada_min} min`;


        document.getElementById(
            "rutaCosto"
        ).textContent =
            `S/ ${datosRuta.costo_delivery.toFixed(2)}`;


        resumen.classList.remove(
            "d-none"
        );


        mensaje.textContent =
            "Ruta de entrega calculada correctamente.";


        boton.disabled =
            false;


        ajustarMapaARuta();


    } catch (error) {

        console.error(
            "Error calculando ruta:",
            error
        );


        resumen.classList.add(
            "d-none"
        );


        boton.disabled =
            true;


        mensaje.textContent =
            "No se pudo calcular la ruta. Selecciona otra ubicación.";

    }

}
/* ========================================================
   AJUSTAR MAPA A TODA LA RUTA
======================================================== */

function ajustarMapaARuta() {

    if (
        !sedeActual ||
        !destinoEntrega ||
        !mapaEntrega
    ) {
        return;
    }


    const limites =
        new google.maps.LatLngBounds();


    limites.extend({
        lat: Number(
            sedeActual.latitud
        ),

        lng: Number(
            sedeActual.longitud
        )
    });


    limites.extend({
        lat: Number(
            destinoEntrega.lat
        ),

        lng: Number(
            destinoEntrega.lng
        )
    });


    mapaEntrega.fitBounds(
        limites,
        70
    );

}
/* ========================================================
   RESUMEN FINAL
======================================================== */

function configurarResumenPedido() {

    const botonDestino =
        document.getElementById(
            "btnDestinoListo"
        );

    const botonConfirmar =
        document.getElementById(
            "btnConfirmarPedido"
        );


    botonDestino.addEventListener(
        "click",
        abrirResumenPedido
    );


    botonConfirmar.addEventListener(
        "click",
        confirmarPedido
    );

}


/* ========================================================
   ABRIR RESUMEN
======================================================== */

function abrirResumenPedido() {

    const nombre =
        document.getElementById(
            "destinatarioNombre"
        ).value.trim();


    const telefono =
        document.getElementById(
            "destinatarioTelefono"
        ).value.trim();


    if (!nombre) {

        alert(
            "Ingresa el nombre del destinatario."
        );

        return;
    }


    if (!telefono) {

        alert(
            "Ingresa el teléfono del destinatario."
        );

        return;
    }


    if (!destinoEntrega) {

        alert(
            "Selecciona una ubicación de entrega."
        );

        return;
    }


    if (
        !datosRuta.distancia_km ||
        !datosRuta.duracion_estimada_min
    ) {

        alert(
            "Primero debemos calcular la ruta."
        );

        return;
    }


    /* =============================================
       DATOS DEL CLIENTE
    ============================================= */

    document.getElementById(
        "resumenDestinatario"
    ).textContent =
        nombre;


    document.getElementById(
        "resumenTelefono"
    ).textContent =
        telefono;


    document.getElementById(
        "resumenDireccion"
    ).textContent =
        destinoEntrega.direccion;


    /* =============================================
       PRODUCTOS
    ============================================= */

    const contenedor =
        document.getElementById(
            "resumenProductos"
        );


    contenedor.innerHTML = "";


    let subtotal = 0;

    let tiempoPreparacion = 0;


    carrito.forEach(
        item => {

            const subtotalItem =
                item.precio *
                item.cantidad;


            subtotal +=
                subtotalItem;


            tiempoPreparacion =
                Math.max(
                    tiempoPreparacion,
                    item.tiempo_preparacion_min
                );


            contenedor.innerHTML += `
                <div class="resumen-producto-item">

                    <div>

                        <strong>
                            ${item.cantidad}
                            ×
                            ${escaparHtml(
                                item.nombre
                            )}
                        </strong>

                        <small
                            class="
                                d-block
                                text-secondary
                            "
                        >
                            S/
                            ${item.precio.toFixed(2)}
                            c/u
                        </small>

                    </div>

                    <strong>
                        S/
                        ${subtotalItem.toFixed(2)}
                    </strong>

                </div>
            `;

        }
    );


    /* =============================================
       RUTA
    ============================================= */

    document.getElementById(
        "resumenDistancia"
    ).textContent =
        `${datosRuta.distancia_km} km`;


    document.getElementById(
        "resumenTiempoRuta"
    ).textContent =
        `${datosRuta.duracion_estimada_min} min`;


    document.getElementById(
        "resumenPreparacion"
    ).textContent =
        `${tiempoPreparacion} min`;


    /* =============================================
       TOTALES PREVIOS
    ============================================= */

    const delivery =
        Number(
            datosRuta.costo_delivery
        );


    const total =
        subtotal +
        delivery;


    document.getElementById(
        "resumenSubtotal"
    ).textContent =
        `S/ ${subtotal.toFixed(2)}`;


    document.getElementById(
        "resumenDelivery"
    ).textContent =
        `S/ ${delivery.toFixed(2)}`;


    document.getElementById(
        "resumenTotal"
    ).textContent =
        `S/ ${total.toFixed(2)}`;


    /* =============================================
       CAMBIAR DE MODAL
    ============================================= */

    const modalEntregaElemento =
        document.getElementById(
            "modalEntrega"
        );


    const modalEntrega =
        bootstrap.Modal.getInstance(
            modalEntregaElemento
        );


    if (modalEntrega) {
        modalEntrega.hide();
    }


    setTimeout(
        () => {

            const modalResumen =
                bootstrap.Modal.getOrCreateInstance(
                    document.getElementById(
                        "modalResumenPedido"
                    )
                );


            modalResumen.show();

        },
        250
    );

}
/* ========================================================
   CONFIRMAR Y REGISTRAR PEDIDO
======================================================== */

async function confirmarPedido() {

    const boton =
        document.getElementById(
            "btnConfirmarPedido"
        );


    const mensaje =
        document.getElementById(
            "mensajeConfirmacion"
        );


    const token =
        localStorage.getItem(
            "kimbos_token"
        );


    if (!token) {

        mostrarMensaje(
            mensaje,
            "Tu sesión terminó. Inicia sesión nuevamente.",
            false
        );

        return;
    }


    if (
        carrito.length === 0 ||
        !destinoEntrega ||
        !datosRuta.distancia_km
    ) {

        mostrarMensaje(
            mensaje,
            "Faltan datos para registrar el pedido.",
            false
        );

        return;
    }


    const nombre =
        document.getElementById(
            "destinatarioNombre"
        ).value.trim();


    const telefono =
        document.getElementById(
            "destinatarioTelefono"
        ).value.trim();


    const metodoPago =
        document.getElementById(
            "metodoPago"
        ).value;


    const indicaciones =
        document.getElementById(
            "indicacionesEntrega"
        ).value.trim();


    const items =
        carrito.map(
            item => ({
                producto_id:
                    item.id,

                cantidad:
                    item.cantidad
            })
        );


    const pedido = {

        destinatario_nombre:
            nombre,

        destinatario_telefono:
            telefono,

        direccion_destino:
            destinoEntrega.direccion,

        latitud_destino:
            destinoEntrega.lat,

        longitud_destino:
            destinoEntrega.lng,

        distancia_km:
            datosRuta.distancia_km,

        duracion_estimada_min:
            datosRuta.duracion_estimada_min,

        metodo_pago:
            metodoPago,

        indicaciones_entrega:
            indicaciones || null,

        items:
            items
    };


    boton.disabled =
        true;


    boton.textContent =
        "Registrando pedido...";


    mensaje.classList.add(
        "d-none"
    );


    try {

        const respuesta =
            await fetch(
                "/api/pedidos",
                {
                    method:
                        "POST",

                    headers: {

                        "Content-Type":
                            "application/json",

                        "Authorization":
                            `Bearer ${token}`
                    },

                    body:
                        JSON.stringify(
                            pedido
                        )
                }
            );


        const datos =
            await respuesta.json();


        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            mostrarMensaje(
                mensaje,
                datos.mensaje ||
                "No se pudo registrar el pedido.",
                false
            );


            boton.disabled =
                false;


            boton.textContent =
                "Confirmar pedido";


            return;
        }


        mostrarPedidoExitoso(
            datos.pedido
        );


    } catch (error) {

        console.error(
            error
        );


        mostrarMensaje(
            mensaje,
            "No se pudo conectar con el servidor.",
            false
        );


        boton.disabled =
            false;


        boton.textContent =
            "Confirmar pedido";

    }

}
/* ========================================================
   PEDIDO REGISTRADO
======================================================== */

function mostrarPedidoExitoso(
    pedido
) {

    document.getElementById(
        "codigoPedidoExito"
    ).textContent =
        pedido.codigo;


    document.getElementById(
        "totalPedidoExito"
    ).textContent =
        `S/ ${Number(
            pedido.total
        ).toFixed(2)}`;


    document.getElementById(
        "tiempoPedidoExito"
    ).textContent =
        `${pedido.tiempo_estimado_total_min} min`;


    /* =============================================
       LIMPIAR CARRITO
    ============================================= */

    carrito = [];

    actualizarCarrito();


    /* =============================================
       CERRAR RESUMEN
    ============================================= */

    const modalResumen =
        bootstrap.Modal.getInstance(
            document.getElementById(
                "modalResumenPedido"
            )
        );


    if (modalResumen) {
        modalResumen.hide();
    }


    /* =============================================
       MOSTRAR ÉXITO
    ============================================= */

    setTimeout(
        () => {

            const modalExito =
                bootstrap.Modal.getOrCreateInstance(
                    document.getElementById(
                        "modalPedidoExito"
                    )
                );


            modalExito.show();

        },
        250
    );

}
/* ========================================================
   MIS PEDIDOS
======================================================== */

function configurarMisPedidos() {

    const boton =
        document.getElementById(
            "btnMisPedidos"
        );

    boton.addEventListener(
        "click",
        abrirMisPedidos
    );

}


/* ========================================================
   ABRIR MIS PEDIDOS
======================================================== */

async function abrirMisPedidos() {

    const token =
        localStorage.getItem(
            "kimbos_token"
        );

    if (!token) {

        abrirModalAcceso();
        return;

    }

    const modal =
        bootstrap.Modal.getOrCreateInstance(
            document.getElementById(
                "modalMisPedidos"
            )
        );

    modal.show();

    await cargarMisPedidos();

}


/* ========================================================
   CARGAR PEDIDOS
======================================================== */

async function cargarMisPedidos() {

    const token =
        localStorage.getItem(
            "kimbos_token"
        );

    const cargando =
        document.getElementById(
            "cargandoPedidos"
        );

    const sinPedidos =
        document.getElementById(
            "sinPedidos"
        );

    const lista =
        document.getElementById(
            "listaMisPedidos"
        );

    const error =
        document.getElementById(
            "errorMisPedidos"
        );

    cargando.classList.remove(
        "d-none"
    );

    sinPedidos.classList.add(
        "d-none"
    );

    error.classList.add(
        "d-none"
    );

    lista.innerHTML = "";

    try {

        const respuesta =
            await fetch(
                "/api/pedidos/mis-pedidos",
                {
                    headers: {
                        "Authorization":
                            `Bearer ${token}`
                    }
                }
            );

        const datos =
            await respuesta.json();

        cargando.classList.add(
            "d-none"
        );

        if (
            !respuesta.ok ||
            !datos.ok
        ) {

            throw new Error(
                datos.mensaje ||
                "No se pudieron cargar los pedidos."
            );

        }

        if (
            !datos.pedidos ||
            datos.pedidos.length === 0
        ) {

            sinPedidos.classList.remove(
                "d-none"
            );

            return;

        }

        renderizarMisPedidos(
            datos.pedidos
        );

    } catch (err) {

        cargando.classList.add(
            "d-none"
        );

        error.textContent =
            err.message;

        error.classList.remove(
            "d-none"
        );

        console.error(err);

    }

}
/* ========================================================
   4 ESTADOS VISIBLES DEL DELIVERY
======================================================== */

const flujoCliente = [

    {
        codigo: "RECIBIDO",
        nombre: "Pedido recibido"
    },

    {
        codigo: "PREPARACION",
        nombre: "En preparación"
    },

    {
        codigo: "CAMINO",
        nombre: "En camino"
    },

    {
        codigo: "ENTREGADO",
        nombre: "Entregado"
    }

];
function obtenerEstadoVisible(
    estadoInterno
) {

    if (
        estadoInterno === "REGISTRADO" ||
        estadoInterno === "CONFIRMADO"
    ) {

        return "RECIBIDO";

    }


    if (
        estadoInterno === "PREPARANDO" ||
        estadoInterno === "LISTO_RECOJO"
    ) {

        return "PREPARACION";

    }


    if (
        estadoInterno === "ASIGNADO" ||
        estadoInterno === "RECOGIDO" ||
        estadoInterno === "EN_RUTA"
    ) {

        return "CAMINO";

    }


    if (
        estadoInterno === "ENTREGADO"
    ) {

        return "ENTREGADO";

    }


    return "RECIBIDO";

}
function renderizarMisPedidos(
    pedidos
) {

    const lista =
        document.getElementById(
            "listaMisPedidos"
        );

    lista.innerHTML = "";


    pedidos.forEach(
        pedido => {

            const productos =
                pedido.productos
                    .map(
                        producto => `
                            <div class="pedido-producto">

                                <span>
                                    ${producto.cantidad}
                                    ×
                                    ${escaparHtml(
                                        producto.nombre
                                    )}
                                </span>

                                <strong>
                                    S/
                                    ${Number(
                                        producto.subtotal
                                    ).toFixed(2)}
                                </strong>

                            </div>
                        `
                    )
                    .join("");


            const seguimiento =
                construirSeguimientoSimple(
                    pedido.estado.codigo
                );


            lista.innerHTML += `
                <div class="pedido-cliente-card">

                    <div
                        class="
                            d-flex
                            justify-content-between
                            align-items-start
                            gap-3
                        "
                    >

                        <div>

                            <div class="pedido-codigo">
                                ${escaparHtml(
                                    pedido.codigo
                                )}
                            </div>

                            <div class="pedido-fecha">
                                ${formatearFechaPedido(
                                    pedido.fecha_pedido
                                )}
                            </div>

                        </div>


                        <div class="text-end">

                            <small class="text-secondary">
                                Total
                            </small>

                            <div class="pedido-total">
                                S/
                                ${Number(
                                    pedido.total
                                ).toFixed(2)}
                            </div>

                        </div>

                    </div>


                    <div class="pedido-productos">

                        ${productos}

                    </div>


                    ${seguimiento}

                </div>
            `;

        }
    );

}
function construirSeguimientoSimple(
    estadoInterno
) {

    const estadoVisible =
        obtenerEstadoVisible(
            estadoInterno
        );


    const indiceActual =
        flujoCliente.findIndex(
            estado =>
                estado.codigo ===
                estadoVisible
        );


    let html = `
        <div class="seguimiento-simple">

            <h6 class="fw-bold">
                Estado del pedido
            </h6>
    `;


    flujoCliente.forEach(
        (estado, indice) => {

            let clase = "";


            if (
                indice < indiceActual
            ) {

                clase =
                    "completado";

            }


            if (
                indice === indiceActual
            ) {

                clase =
                    "actual";

            }


            html += `
                <div
                    class="
                        estado-simple
                        ${clase}
                    "
                >

                    <div class="estado-icono">

                        <div class="estado-circulo">
                        </div>

                        <div class="estado-linea">
                        </div>

                    </div>


                    <div class="estado-texto">

                        <strong>
                            ${estado.nombre}
                        </strong>

                    </div>

                </div>
            `;

        }
    );


    html += `
        </div>
    `;


    return html;

}
function formatearFechaPedido(
    fecha
) {

    if (!fecha) {
        return "";
    }

    return new Date(
        fecha
    ).toLocaleString(
        "es-PE",
        {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        }
    );

}
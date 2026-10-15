/* ========================================================
   RESPUESTAS DEL SERVIDOR
   Si el servidor responde con una pagina HTML en vez de JSON
   (se esta reiniciando, desplegando o el internet corto la
   respuesta), se muestra un mensaje entendible en lugar de
   "Unexpected token '<' ... is not valid JSON".
======================================================== */

(function () {

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

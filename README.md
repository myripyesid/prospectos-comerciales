# prospectos-comerciales
app de desktop basica para obtener informacion de clientes y contactarlos a traves de navegacion de google maps

## Reporte de contactos

En la pestaña **4. Reportes**, selecciona una lista CSV de `resultados_csv` e ingresa cuántas personas respondieron y cuántas citas se concretaron. El total cuenta los celulares colombianos únicos de esa lista que aparecen con estado `enviado` en `resultados_csv/whatsapp_envios.csv`. Las citas no pueden superar las respuestas, y las respuestas no pueden superar el total.

Las bases nuevas incluyen la columna `Contactado` (inicia en `No`). El asistente la cambia a `Sí` al abrir el chat manualmente o al confirmar un envío desde el bot. Los reportes cuentan los celulares únicos marcados `Sí`; las bases antiguas se actualizan con los envíos previos del registro de WhatsApp al cargarlas.

Si el registro no refleja todos los contactos hablados, completa **Contactos hablados manualmente (opcional)**. Ese número reemplaza el total automático solo para el reporte; déjalo vacío para usar el registro de WhatsApp.

También puedes escribir un **Nombre de la base (opcional)** para que aparezca en el PDF; si lo dejas vacío, se mostrará el nombre del CSV.

Usa **Exportar reporte en PDF** para guardar el reporte con las tasas de respuesta y citas, un gráfico de barras y un gráfico de pastel con la distribución de resultados. El programa requiere ReportLab para generar los PDF.

Las pruebas del módulo se ejecutan con `python test_reportes.py`.

## Cotizaciones

En la pestaña **5. Cotizaciones** ingresa los datos del cliente, número y fecha, plazo de entrega, garantía y uno o varios productos. La aplicación calcula el total de cada línea y el total general. Puedes exportar a PDF o Excel; ambos formatos incluyen el logo ProAlum y los diálogos abren por defecto dentro de `cotizaciones`, que se crea automáticamente. El Excel incluye fórmulas para que se actualicen los totales al ajustar cantidades o valores.

Las pruebas de cotizaciones se ejecutan con `python test_cotizaciones.py`.

"""Utilidades para calcular y exportar reportes de contactos."""
import csv
import re
from datetime import datetime

import pandas as pd


def _normalizar_celular(telefono):
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if digitos.startswith("57") and len(digitos) == 12:
        digitos = digitos[2:]
    if len(digitos) == 10 and digitos.startswith("3"):
        return f"57{digitos}"
    return None


def preparar_base_contactos(ruta_csv, ruta_log=None):
    """Agrega Contactado a bases antiguas y recupera envíos registrados."""
    df = pd.read_csv(ruta_csv, dtype={"Teléfono": str})
    columnas = {"Nombre", "Teléfono"}
    if not columnas.issubset(df.columns):
        raise ValueError("El CSV debe incluir las columnas 'Nombre' y 'Teléfono'.")

    tenia_columna = "Contactado" in df.columns
    if not tenia_columna:
        df["Contactado"] = "No"
        cambio = True
    else:
        previo = df["Contactado"].astype("object").fillna("No").astype(str)
        normalizado = previo.map(
            lambda valor: "Sí" if _es_contactado(valor) else "No"
        )
        cambio = not normalizado.equals(previo)
        df["Contactado"] = normalizado

    enviados = set()
    if ruta_log:
        try:
            with open(ruta_log, newline="", encoding="utf-8-sig") as archivo:
                lector = csv.DictReader(archivo)
                encabezados = lector.fieldnames or []
                if "numero" not in encabezados or "estado" not in encabezados:
                    raise ValueError("El registro de WhatsApp no contiene las columnas 'numero' y 'estado'.")
                enviados = {
                    celular
                    for fila in lector
                    if fila.get("estado", "").strip().lower() == "enviado"
                    for celular in [_normalizar_celular(fila.get("numero"))]
                    if celular
                }
        except FileNotFoundError:
            pass

    if enviados:
        enviados_en_base = df["Teléfono"].map(_normalizar_celular).isin(enviados)
        if (enviados_en_base & df["Contactado"].ne("Sí")).any():
            cambio = True
        df.loc[enviados_en_base, "Contactado"] = "Sí"

    if cambio:
        df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")
    return df


def _es_contactado(valor):
    return str(valor or "").strip().casefold() in {"sí", "si", "yes", "true", "1"}


def contar_contactos_csv(ruta_csv):
    """Cuenta celulares únicos con Contactado=Sí en la base seleccionada."""
    df = pd.read_csv(ruta_csv, dtype={"Teléfono": str})
    columnas = {"Nombre", "Teléfono", "Contactado"}
    if not columnas.issubset(df.columns):
        raise ValueError("El CSV debe incluir las columnas 'Nombre', 'Teléfono' y 'Contactado'.")

    return len({
        celular
        for _, fila in df.iterrows()
        if pd.notna(fila["Nombre"]) and _es_contactado(fila["Contactado"])
        for celular in [_normalizar_celular(fila["Teléfono"])]
        if celular
    })


def marcar_contactado_csv(ruta_csv, telefono):
    """Marca como contactadas las filas que comparten el celular indicado."""
    celular = _normalizar_celular(telefono)
    if not celular:
        raise ValueError("El teléfono no es un celular colombiano válido.")

    df = preparar_base_contactos(ruta_csv)
    coincidencias = df["Teléfono"].map(_normalizar_celular) == celular
    if not coincidencias.any():
        raise ValueError("No se encontró el teléfono en la base seleccionada.")
    df.loc[coincidencias, "Contactado"] = "Sí"
    df.to_csv(ruta_csv, index=False, encoding="utf-8-sig")


def calcular_metricas(total_contactos, respondieron, citas, total_manual=False):
    if any(not isinstance(valor, int) or isinstance(valor, bool) for valor in
           (total_contactos, respondieron, citas)):
        raise ValueError("Los totales deben ser números enteros.")
    if not isinstance(total_manual, bool):
        raise ValueError("El indicador del total manual debe ser booleano.")
    if total_contactos <= 0:
        raise ValueError("El CSV seleccionado no contiene celulares válidos para reportar.")
    if respondieron < 0 or citas < 0:
        raise ValueError("Las respuestas y las citas no pueden ser negativas.")
    if respondieron > total_contactos:
        raise ValueError("Las respuestas no pueden superar el total de contactos.")
    if citas > respondieron:
        raise ValueError("Las citas no pueden superar el número de personas que respondieron.")

    return {
        "total": total_contactos,
        "total_manual": total_manual,
        "respondieron": respondieron,
        "citas": citas,
        "sin_respuesta": total_contactos - respondieron,
        "respondieron_sin_cita": respondieron - citas,
        "porcentaje_respuesta": respondieron / total_contactos * 100,
        "porcentaje_citas": citas / total_contactos * 100,
    }


def exportar_reporte_pdf(ruta_pdf, nombre_base, metricas):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    pagina = canvas.Canvas(ruta_pdf, pagesize=letter)
    ancho, alto = letter
    azul = colors.HexColor("#2563A6")
    verde = colors.HexColor("#28A879")
    naranja = colors.HexColor("#F2A541")
    gris = colors.HexColor("#667085")
    oscuro = colors.HexColor("#172B4D")

    pagina.setFillColor(oscuro)
    pagina.setFont("Helvetica-Bold", 22)
    pagina.drawString(48, alto - 58, "Reporte de contactos")
    pagina.setFillColor(gris)
    pagina.setFont("Helvetica", 10)
    pagina.drawString(48, alto - 78, f"Base: {nombre_base}")
    pagina.drawString(48, alto - 94, f"Generado: {datetime.now():%d/%m/%Y %H:%M}")

    metricas_resumen = (
        ("Contactos", metricas["total"], azul),
        ("Respondieron", metricas["respondieron"], verde),
        ("Citas concretadas", metricas["citas"], naranja),
    )
    tarjeta_y = alto - 160
    tarjeta_ancho = (ancho - 120) / 3
    for indice, (titulo, valor, color) in enumerate(metricas_resumen):
        x = 48 + indice * (tarjeta_ancho + 12)
        pagina.setFillColor(colors.HexColor("#F3F6FA"))
        pagina.roundRect(x, tarjeta_y, tarjeta_ancho, 48, 7, fill=1, stroke=0)
        pagina.setFillColor(color)
        pagina.setFont("Helvetica-Bold", 18)
        pagina.drawCentredString(x + tarjeta_ancho / 2, tarjeta_y + 25, str(valor))
        pagina.setFillColor(gris)
        pagina.setFont("Helvetica", 9)
        pagina.drawCentredString(x + tarjeta_ancho / 2, tarjeta_y + 10, titulo)

    pagina.setFillColor(oscuro)
    pagina.setFont("Helvetica-Bold", 13)
    pagina.drawString(55, alto - 198, "Porcentaje sobre el total contactado")

    graf_x, graf_y, graf_ancho, graf_alto = 75, alto - 430, 205, 190
    pagina.setStrokeColor(colors.HexColor("#D7DEE8"))
    pagina.line(graf_x, graf_y, graf_x, graf_y + graf_alto)
    pagina.line(graf_x, graf_y, graf_x + graf_ancho, graf_y)
    for porcentaje in (0, 25, 50, 75, 100):
        y = graf_y + graf_alto * porcentaje / 100
        pagina.setStrokeColor(colors.HexColor("#E8EDF3"))
        pagina.line(graf_x, y, graf_x + graf_ancho, y)
        pagina.setFillColor(gris)
        pagina.setFont("Helvetica", 8)
        pagina.drawRightString(graf_x - 6, y - 3, f"{porcentaje}%")

    for indice, (etiqueta, porcentaje, color) in enumerate((
        ("Respuesta", metricas["porcentaje_respuesta"], verde),
        ("Citas", metricas["porcentaje_citas"], azul),
    )):
        x = graf_x + 45 + indice * 90
        altura = graf_alto * porcentaje / 100
        pagina.setFillColor(color)
        pagina.roundRect(x, graf_y, 48, altura, 4, fill=1, stroke=0)
        pagina.setFillColor(oscuro)
        pagina.setFont("Helvetica-Bold", 9)
        pagina.drawCentredString(x + 24, graf_y + altura + 7, f"{porcentaje:.1f}%")
        pagina.setFont("Helvetica", 9)
        pagina.drawCentredString(x + 24, graf_y - 15, etiqueta)

    pagina.setFillColor(oscuro)
    pagina.setFont("Helvetica-Bold", 13)
    pagina.drawString(350, alto - 198, "Resultado de los contactos")

    valores_pastel = (
        ("Sin respuesta", metricas["sin_respuesta"], azul),
        ("Respondieron sin cita", metricas["respondieron_sin_cita"], naranja),
        ("Cita concretada", metricas["citas"], verde),
    )
    centro_x, centro_y, radio = 445, alto - 310, 68
    angulo = 90
    for _, valor, color in valores_pastel:
        if not valor:
            continue
        extension = valor / metricas["total"] * 360
        pagina.setFillColor(color)
        pagina.wedge(
            centro_x - radio, centro_y - radio, centro_x + radio, centro_y + radio,
            angulo, extension, stroke=0, fill=1
        )
        angulo += extension

    for indice, (etiqueta, valor, color) in enumerate(valores_pastel):
        y = centro_y - 88 - indice * 19
        pagina.setFillColor(color)
        pagina.rect(350, y, 9, 9, fill=1, stroke=0)
        pagina.setFillColor(oscuro)
        pagina.setFont("Helvetica", 9)
        porcentaje = valor / metricas["total"] * 100
        pagina.drawString(365, y + 1, f"{etiqueta}: {valor} ({porcentaje:.1f}%)")

    pagina.setStrokeColor(colors.HexColor("#D7DEE8"))
    pagina.line(48, 48, ancho - 48, 48)
    pagina.setFillColor(gris)
    pagina.setFont("Helvetica", 8)
    pie = (
        "Total de contactos indicado manualmente por el usuario."
        if metricas["total_manual"]
        else "Base: celulares unicos del CSV con estado enviado en el registro de WhatsApp."
    )
    pagina.drawString(48, 34, pie)
    pagina.save()

"""Cálculo y exportación de cotizaciones en PDF y Excel."""
import os
import re
from datetime import datetime
from xml.sax.saxutils import escape


def parsear_cantidad(valor):
    texto = str(valor).strip()
    if not re.fullmatch(r"\d+", texto):
        raise ValueError("La cantidad debe ser un número entero positivo.")
    cantidad = int(texto)
    if cantidad < 1:
        raise ValueError("La cantidad debe ser mayor que cero.")
    return cantidad


def parsear_valor(valor):
    texto = str(valor).strip().replace("$", "").replace(" ", "")
    if not texto or not re.fullmatch(r"\d[\d.,]*", texto):
        raise ValueError("El valor debe ser un número entero, por ejemplo 790000 o 790.000.")
    return int(re.sub(r"[.,]", "", texto))


def formatear_pesos(valor):
    return f"$ {valor:,}".replace(",", ".")


def formatear_fecha(valor):
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, formato).strftime("%d/%m/%Y")
        except ValueError:
            pass
    raise ValueError("La fecha debe tener formato AAAA-MM-DD o DD/MM/AAAA.")


def calcular_cotizacion(cliente, nit, direccion, telefono, fecha, numero,
                         items, fecha_entrega, garantia):
    cliente = str(cliente).strip()
    numero = str(numero).strip()
    fecha_entrega = str(fecha_entrega).strip()
    garantia = str(garantia).strip()
    if not cliente:
        raise ValueError("Ingresa el nombre del cliente.")
    if not numero:
        raise ValueError("Ingresa el número de cotización.")
    if not fecha_entrega:
        raise ValueError("Ingresa la fecha o plazo de entrega.")
    if not garantia:
        raise ValueError("Ingresa la garantía.")

    fecha = formatear_fecha(fecha)
    productos = []
    for indice, item in enumerate(items, start=1):
        valores = (
            str(item.get("cantidad", "")).strip(),
            str(item.get("descripcion", "")).strip(),
            str(item.get("valor_unitario", "")).strip(),
        )
        if not any(valores):
            continue
        cantidad_texto, descripcion, valor_texto = valores
        if not descripcion:
            raise ValueError(f"Falta la descripción del producto {indice}.")
        cantidad = parsear_cantidad(cantidad_texto)
        valor_unitario = parsear_valor(valor_texto)
        productos.append({
            "cantidad": cantidad,
            "descripcion": descripcion,
            "valor_unitario": valor_unitario,
            "valor_total": cantidad * valor_unitario,
        })

    if not productos:
        raise ValueError("Agrega al menos un producto a la cotización.")

    subtotal = sum(producto["valor_total"] for producto in productos)
    return {
        "cliente": cliente,
        "nit": str(nit).strip(),
        "direccion": str(direccion).strip(),
        "telefono": str(telefono).strip(),
        "fecha": fecha,
        "numero": numero,
        "items": productos,
        "fecha_entrega": fecha_entrega,
        "garantia": garantia,
        "subtotal": subtotal,
        "total": subtotal,
    }


def exportar_pdf(ruta_pdf, cotizacion):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import (
        Image, LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    azul = colors.HexColor("#00A9DC")
    azul_claro = colors.HexColor("#EAF8FC")
    gris = colors.HexColor("#555555")
    negro = colors.HexColor("#202020")
    amarillo = colors.HexColor("#FFF200")
    doc = SimpleDocTemplate(
        ruta_pdf, pagesize=landscape(A4),
        leftMargin=28, rightMargin=28, topMargin=24, bottomMargin=24,
        title=f"Cotización {cotizacion['numero']}",
    )
    ancho = doc.width
    muestras = getSampleStyleSheet()
    normal = ParagraphStyle(
        "CotizacionNormal", parent=muestras["Normal"], fontName="Helvetica",
        fontSize=8, leading=10, textColor=negro,
    )
    centrado = ParagraphStyle("CotizacionCentrado", parent=normal, alignment=1)
    etiqueta = ParagraphStyle(
        "CotizacionEtiqueta", parent=normal, fontName="Helvetica-Bold",
        backColor=azul_claro,
    )
    encabezado = ParagraphStyle(
        "CotizacionEncabezado", parent=centrado, fontName="Helvetica-Bold",
        textColor=colors.white, fontSize=8,
    )
    empresa = ParagraphStyle(
        "CotizacionEmpresa", parent=centrado, fontName="Helvetica-Bold",
        fontSize=10, leading=13,
    )

    def parrafo(texto, estilo=normal):
        return Paragraph(escape(str(texto or "-")).replace("\n", "<br/>"), estilo)

    celdas_empresa = Paragraph(
        '<b>PROYECTOS EN VIDRIO Y ALUMINIO</b><br/>'
        'DIR. CALLE 36 # 50A 79, SECTOR INDUAMÉRICA, ITAGÜÍ<br/>'
        'CEL. 3186996209 - 3166955089<br/>NIT: 13742467-7',
        empresa,
    )
    logo = Image(
        os.path.join(os.path.dirname(__file__), "assets", "proalum_logo.png"),
        width=72, height=52, kind="proportional",
    )
    caja_numero = Table([
        [parrafo("COTIZACIÓN N.º", encabezado)],
        [parrafo(cotizacion["numero"], centrado)],
    ], colWidths=[112])
    caja_numero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), azul),
        ("BOX", (0, 0), (-1, -1), 1.2, negro),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, negro),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    cabecera = Table(
        [[logo, celdas_empresa, caja_numero]],
        colWidths=[78, ancho - 190, 112],
    )
    cabecera.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, negro),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    datos_cliente = Table([
        [parrafo("CLIENTE", etiqueta), parrafo(cotizacion["cliente"]),
         parrafo("TEL.", etiqueta), parrafo(cotizacion["telefono"])],
        [parrafo("NIT", etiqueta), parrafo(cotizacion["nit"]),
         parrafo("FECHA", etiqueta), parrafo(cotizacion["fecha"])],
        [parrafo("DIRECCIÓN", etiqueta), parrafo(cotizacion["direccion"]), "", ""],
    ], colWidths=[62, ancho - 62 - 50 - 195, 50, 195])
    datos_cliente.setStyle(TableStyle([
        ("SPAN", (1, 2), (3, 2)),
        ("GRID", (0, 0), (-1, -1), 0.8, negro),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    historia = [
        cabecera,
        Spacer(1, 5),
        datos_cliente,
        Spacer(1, 6),
        parrafo(
            "Presentamos la cotización de los productos y servicios solicitados.",
            centrado,
        ),
        Spacer(1, 5),
    ]

    filas = [[
        parrafo("CANT.", encabezado),
        parrafo("DESCRIPCIÓN", encabezado),
        parrafo("VALOR UNITARIO", encabezado),
        parrafo("VALOR TOTAL", encabezado),
    ]]
    for item in cotizacion["items"]:
        filas.append([
            parrafo(item["cantidad"], centrado),
            parrafo(item["descripcion"]),
            parrafo(formatear_pesos(item["valor_unitario"]), centrado),
            parrafo(formatear_pesos(item["valor_total"]), centrado),
        ])
    tabla_items = LongTable(
        filas,
        colWidths=[48, ancho - 48 - 112 - 130, 130, 112],
        repeatRows=1,
    )
    tabla_items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("GRID", (0, 0), (-1, -1), 0.7, negro),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    historia.append(tabla_items)
    historia.append(Spacer(1, 6))

    beneficios = Table([
        [parrafo("NUESTROS BENEFICIOS", centrado)],
        [parrafo("1. Utilizamos vidrios de excelente calidad.")],
        [parrafo("2. Garantizamos que su producto llegue en óptimas condiciones.")],
    ], colWidths=[ancho - 245])
    beneficios.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, negro),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, negro),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    totales = Table([
        [parrafo("SUBTOTAL", encabezado), parrafo(formatear_pesos(cotizacion["subtotal"]), centrado)],
        [parrafo("TOTAL", encabezado), parrafo(formatear_pesos(cotizacion["total"]), centrado)],
    ], colWidths=[90, 155])
    totales.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), azul),
        ("BOX", (0, 0), (-1, -1), 0.8, negro),
        ("INNERGRID", (0, 0), (-1, -1), 0.7, negro),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    resumen = Table([[beneficios, totales]], colWidths=[ancho - 245, 245])
    resumen.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    historia.extend([
        resumen,
        Spacer(1, 6),
        parrafo(f"FECHA DE ENTREGA: {cotizacion['fecha_entrega']}"),
    ])
    garantia = Table([[parrafo(f"GARANTÍA: {cotizacion['garantia']}", etiqueta)]],
                     colWidths=[ancho])
    garantia.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), amarillo),
        ("BOX", (0, 0), (-1, -1), 0.8, negro),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    historia.append(garantia)
    doc.build(historia)


def exportar_excel(ruta_xlsx, cotizacion):
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as ExcelImage
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    azul = "00A9DC"
    azul_claro = "EAF8FC"
    amarillo = "FFF200"
    negro = "202020"
    borde = Side(style="thin", color=negro)
    borde_exterior = Border(left=borde, right=borde, top=borde, bottom=borde)
    relleno_azul = PatternFill("solid", fgColor=azul)
    relleno_claro = PatternFill("solid", fgColor=azul_claro)
    relleno_amarillo = PatternFill("solid", fgColor=amarillo)
    negrita = Font(name="Arial", bold=True, color=negro)
    centrado = Alignment(horizontal="center", vertical="center", wrap_text=True)
    izquierda = Alignment(horizontal="left", vertical="center", wrap_text=True)
    derecha = Alignment(horizontal="right", vertical="center")

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Cotización"
    hoja.sheet_view.showGridLines = False
    hoja.column_dimensions["A"].width = 12
    hoja.column_dimensions["B"].width = 64
    hoja.column_dimensions["C"].width = 20
    hoja.column_dimensions["D"].width = 20

    hoja.merge_cells("B1:C1")
    hoja["B1"] = "PROALUM | PROYECTOS EN VIDRIO Y ALUMINIO"
    hoja.merge_cells("B2:C2")
    hoja["B2"] = (
        "DIR. CALLE 36 # 50A 79, SECTOR INDUAMÉRICA, ITAGÜÍ | "
        "CEL. 3186996209 - 3166955089 | NIT: 13742467-7"
    )
    logo = ExcelImage(os.path.join(os.path.dirname(__file__), "assets", "proalum_logo.png"))
    logo.width = 78
    logo.height = 55
    hoja.add_image(logo, "A1")
    hoja["D1"] = "COTIZACIÓN N.º"
    hoja["D2"] = cotizacion["numero"]
    hoja.row_dimensions[1].height = 30
    hoja.row_dimensions[2].height = 28
    hoja["B1"].font = Font(name="Arial", size=16, bold=True, color=azul)
    hoja["B1"].alignment = centrado
    hoja["B2"].font = Font(name="Arial", size=9, bold=True)
    hoja["B2"].alignment = centrado
    for coordenada in ("D1", "D2"):
        hoja[coordenada].alignment = centrado
        hoja[coordenada].border = borde_exterior
    hoja["D1"].fill = relleno_azul
    hoja["D1"].font = negrita
    hoja["D2"].font = Font(name="Arial", size=12, bold=True)

    filas_cliente = [
        ("CLIENTE", cotizacion["cliente"], f"TEL.: {cotizacion['telefono'] or '-'}"),
        ("NIT", cotizacion["nit"] or "-", f"FECHA: {cotizacion['fecha']}"),
    ]
    for fila, (etiqueta, valor, adicional) in enumerate(filas_cliente, start=4):
        hoja.cell(fila, 1, etiqueta)
        hoja.cell(fila, 2, valor)
        hoja.merge_cells(start_row=fila, start_column=2, end_row=fila, end_column=3)
        hoja.cell(fila, 4, adicional)
        hoja.row_dimensions[fila].height = 24
    hoja["A6"] = "DIRECCIÓN"
    hoja["B6"] = cotizacion["direccion"] or "-"
    hoja.merge_cells("B6:D6")
    hoja.row_dimensions[6].height = 26
    for fila in range(4, 7):
        for columna in range(1, 5):
            celda = hoja.cell(fila, columna)
            celda.border = borde_exterior
            celda.alignment = izquierda if columna in (2, 3) else centrado
            if columna == 1:
                celda.fill = relleno_claro
                celda.font = negrita

    hoja.merge_cells("A8:D8")
    hoja["A8"] = "Presentamos la cotización de los productos y servicios solicitados."
    hoja["A8"].alignment = centrado

    encabezado_fila = 10
    titulos = ("CANT.", "DESCRIPCIÓN", "VALOR UNITARIO", "VALOR TOTAL")
    for columna, titulo in enumerate(titulos, start=1):
        celda = hoja.cell(encabezado_fila, columna, titulo)
        celda.fill = relleno_azul
        celda.font = negrita
        celda.alignment = centrado
        celda.border = borde_exterior

    primera_fila_item = encabezado_fila + 1
    for desplazamiento, item in enumerate(cotizacion["items"]):
        fila = primera_fila_item + desplazamiento
        hoja.cell(fila, 1, item["cantidad"])
        hoja.cell(fila, 2, item["descripcion"])
        hoja.cell(fila, 3, item["valor_unitario"])
        hoja.cell(fila, 4, f"=A{fila}*C{fila}")
        hoja.row_dimensions[fila].height = max(24, min(72, 18 + len(item["descripcion"]) // 65 * 12))
        for columna in range(1, 5):
            celda = hoja.cell(fila, columna)
            celda.border = borde_exterior
            celda.alignment = izquierda if columna == 2 else derecha
            if columna in (3, 4):
                celda.number_format = '"$" #,##0'

    ultima_fila_item = primera_fila_item + len(cotizacion["items"]) - 1
    fila_subtotal = ultima_fila_item + 1
    fila_total = fila_subtotal + 1
    hoja.cell(fila_subtotal, 3, "SUBTOTAL")
    hoja.cell(fila_subtotal, 4, f"=SUM(D{primera_fila_item}:D{ultima_fila_item})")
    hoja.cell(fila_total, 3, "TOTAL")
    hoja.cell(fila_total, 4, f"=D{fila_subtotal}")
    for fila in (fila_subtotal, fila_total):
        for columna in (3, 4):
            celda = hoja.cell(fila, columna)
            celda.border = borde_exterior
            celda.alignment = derecha
            celda.font = negrita
        hoja.cell(fila, 3).fill = relleno_azul
        hoja.cell(fila, 4).number_format = '"$" #,##0'

    fila_beneficios = fila_total + 2
    hoja.merge_cells(start_row=fila_beneficios, start_column=1,
                     end_row=fila_beneficios, end_column=4)
    hoja.cell(fila_beneficios, 1, "NUESTROS BENEFICIOS")
    hoja.cell(fila_beneficios, 1).font = negrita
    hoja.cell(fila_beneficios, 1).alignment = centrado
    beneficios = (
        "1. Utilizamos vidrios de excelente calidad.",
        "2. Garantizamos que su producto llegue en óptimas condiciones.",
    )
    for desplazamiento, texto in enumerate(beneficios, start=1):
        fila = fila_beneficios + desplazamiento
        hoja.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=4)
        hoja.cell(fila, 1, texto)
        hoja.cell(fila, 1).alignment = izquierda

    fila_entrega = fila_beneficios + len(beneficios) + 1
    hoja.merge_cells(start_row=fila_entrega, start_column=1, end_row=fila_entrega, end_column=4)
    hoja.cell(fila_entrega, 1, f"FECHA DE ENTREGA: {cotizacion['fecha_entrega']}")
    hoja.cell(fila_entrega, 1).alignment = izquierda
    fila_garantia = fila_entrega + 1
    hoja.merge_cells(start_row=fila_garantia, start_column=1, end_row=fila_garantia, end_column=4)
    hoja.cell(fila_garantia, 1, f"GARANTÍA: {cotizacion['garantia']}")
    hoja.cell(fila_garantia, 1).fill = relleno_amarillo
    hoja.cell(fila_garantia, 1).font = negrita
    hoja.cell(fila_garantia, 1).alignment = izquierda
    for fila in range(fila_beneficios, fila_garantia + 1):
        for columna in range(1, 5):
            hoja.cell(fila, columna).border = borde_exterior

    hoja.freeze_panes = f"A{primera_fila_item}"
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.print_area = f"A1:D{fila_garantia}"
    libro.properties.title = f"Cotización {cotizacion['numero']}"
    libro.calculation.fullCalcOnLoad = True
    libro.calculation.forceFullCalc = True
    libro.calculation.calcMode = "auto"
    libro.save(ruta_xlsx)

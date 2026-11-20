"""
Cálculo de liquidación de contrato de trabajo (Colombia, Código Sustantivo del Trabajo).

Módulo sin interfaz: solo funciones puras, para poder probarlas por separado.
Valores de referencia 2026 (editables desde la UI):
  - SMMLV 2026:              $1.750.905  (Decreto 1469/2025; mantenido por el Decreto 0159/2026,
                                          provisional hasta fallo del Consejo de Estado)
  - Auxilio de transporte:   $249.095    (Decreto 1470/2025)

Supuestos (año comercial de 360 días, meses de 30 días):
  - Cesantías:            base * días / 360          (art. 249 CST). Base = salario (+ aux. transporte).
  - Intereses cesantías:  cesantías * días * 12% / 360 (Ley 52/1975).
  - Prima de servicios:   base * días del semestre / 360 (art. 306 CST). Base = salario (+ aux. transp.).
  - Vacaciones:           salario * días pendientes / 30; 15 días hábiles por año (art. 186 CST).
                          Base SIN auxilio de transporte.
  - Indemnización (art. 64 CST, solo despido sin justa causa), base SIN auxilio de transporte:
      * Indefinido, salario < 10 SMMLV: 30 días el primer año + 20 por cada año adicional (proporcional).
      * Indefinido, salario >= 10 SMMLV: 20 días el primer año + 15 por cada año adicional (proporcional).
      * Fijo: salarios del tiempo que falte para el vencimiento del plazo pactado.
      * Obra o labor: salarios del tiempo que falte, mínimo 15 días.

No incluye: indemnización moratoria (art. 65), horas extra/recargos pendientes, descuentos de nómina
(salud/pensión sobre el salario pendiente, retención, préstamos) ni casos especiales (fuero, salario integral).
Es una herramienta de apoyo, no asesoría legal.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import calendar

SMMLV_2026 = 1_750_905
AUXILIO_TRANSPORTE_2026 = 249_095
TASA_INTERESES_CESANTIAS = 0.12

TIPOS_CONTRATO = ["Indefinido", "Fijo", "Obra o labor"]
MOTIVOS = [
    "Renuncia",
    "Despido sin justa causa",
    "Despido con justa causa",
    "Mutuo acuerdo / vencimiento del plazo",
]


# ---------------------------------------------------------------- fechas
def parsear_fecha(texto):
    """Acepta AAAA-MM-DD o DD/MM/AAAA. Lanza ValueError si no es válida."""
    texto = texto.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha no válida: '{texto}'. Usa AAAA-MM-DD o DD/MM/AAAA.")


def _es_fin_de_febrero(d):
    return d.month == 2 and d.day == calendar.monthrange(d.year, 2)[1]


def dias_360(inicio, fin):
    """Días entre dos fechas, ambas INCLUIDAS, con calendario comercial (meses de 30 días).
    El día 31 y el último día de febrero de la fecha final cuentan como 30."""
    if fin < inicio:
        return 0
    d1 = min(inicio.day, 30)
    d2 = 30 if (fin.day == 31 or _es_fin_de_febrero(fin)) else fin.day
    return (fin.year - inicio.year) * 360 + (fin.month - inicio.month) * 30 + (d2 - d1)


# ---------------------------------------------------------------- resultado
@dataclass
class Concepto:
    nombre: str
    valor: int
    detalle: str = ""


@dataclass
class Liquidacion:
    conceptos: list = field(default_factory=list)
    advertencias: list = field(default_factory=list)
    dias_totales: int = 0
    aplica_auxilio: bool = False

    @property
    def total(self):
        return sum(c.valor for c in self.conceptos)


def _pesos(x):
    return int(round(x))


def formato_pesos(valor):
    return "$" + f"{int(valor):,}".replace(",", ".")


# ---------------------------------------------------------------- cálculo
def calcular_liquidacion(
    fecha_ingreso,
    fecha_retiro,
    salario_mensual,
    tipo_contrato="Indefinido",
    motivo="Renuncia",
    fecha_fin_pactada=None,
    salario_promedio=None,
    auxilio="Auto",                 # "Auto" | "Sí" | "No"
    dias_vacaciones_disfrutados=0.0,  # días hábiles ya disfrutados o compensados
    dias_salario_pendiente=0,         # días trabajados y no pagados
    cesantias_desde=None,             # si NO se han consignado, desde cuándo se adeudan
    prima_desde=None,                 # si NO se ha pagado, desde cuándo se adeuda
    smmlv=SMMLV_2026,
    auxilio_transporte=AUXILIO_TRANSPORTE_2026,
):
    if fecha_retiro < fecha_ingreso:
        raise ValueError("La fecha de retiro no puede ser anterior a la de ingreso.")
    if salario_mensual <= 0:
        raise ValueError("El salario debe ser mayor que cero.")
    if tipo_contrato not in TIPOS_CONTRATO:
        raise ValueError(f"Tipo de contrato desconocido: {tipo_contrato}")
    if motivo not in MOTIVOS:
        raise ValueError(f"Motivo desconocido: {motivo}")

    liq = Liquidacion()
    liq.dias_totales = dias_360(fecha_ingreso, fecha_retiro)

    # --- base de prestaciones (salario + auxilio de transporte si aplica)
    salario_base = salario_promedio if salario_promedio else salario_mensual
    if auxilio == "Sí":
        aplica_aux = True
    elif auxilio == "No":
        aplica_aux = False
    else:
        aplica_aux = salario_base <= 2 * smmlv
    liq.aplica_auxilio = aplica_aux
    base_prest = salario_base + (auxilio_transporte if aplica_aux else 0)

    # --- salario pendiente
    if dias_salario_pendiente > 0:
        valor = salario_mensual / 30 * dias_salario_pendiente
        if aplica_aux:
            valor += auxilio_transporte / 30 * dias_salario_pendiente
        liq.conceptos.append(Concepto(
            "Salario pendiente", _pesos(valor),
            f"{dias_salario_pendiente} días" + (" (incluye auxilio de transporte)" if aplica_aux else "")))
        liq.advertencias.append(
            "Salario pendiente se muestra bruto: faltan descuentos de salud/pensión (4% + 4%) y otros.")

    # --- cesantías
    inicio_ces = cesantias_desde or max(fecha_ingreso, date(fecha_retiro.year, 1, 1))
    inicio_ces = max(inicio_ces, fecha_ingreso)
    dias_ces = dias_360(inicio_ces, fecha_retiro)
    cesantias = base_prest * dias_ces / 360
    liq.conceptos.append(Concepto(
        "Cesantías", _pesos(cesantias),
        f"{formato_pesos(base_prest)} × {dias_ces} días / 360 (desde {inicio_ces})"))

    # --- intereses sobre cesantías
    intereses = cesantias * dias_ces * TASA_INTERESES_CESANTIAS / 360
    liq.conceptos.append(Concepto(
        "Intereses sobre cesantías", _pesos(intereses),
        f"cesantías × {dias_ces} días × 12% / 360"))

    # --- prima de servicios (semestre en curso)
    inicio_semestre = date(fecha_retiro.year, 1 if fecha_retiro.month <= 6 else 7, 1)
    inicio_prima = prima_desde or max(fecha_ingreso, inicio_semestre)
    inicio_prima = max(inicio_prima, fecha_ingreso)
    dias_prima = dias_360(inicio_prima, fecha_retiro)
    prima = base_prest * dias_prima / 360
    liq.conceptos.append(Concepto(
        "Prima de servicios", _pesos(prima),
        f"{formato_pesos(base_prest)} × {dias_prima} días / 360 (desde {inicio_prima})"))

    # --- vacaciones (base sin auxilio de transporte)
    dias_causados = liq.dias_totales * 15 / 360
    dias_pendientes = max(0.0, dias_causados - dias_vacaciones_disfrutados)
    vacaciones = salario_mensual / 30 * dias_pendientes
    liq.conceptos.append(Concepto(
        "Vacaciones", _pesos(vacaciones),
        f"{dias_pendientes:.2f} días hábiles pendientes "
        f"({dias_causados:.2f} causados − {dias_vacaciones_disfrutados:g} disfrutados) × salario/30"))

    # --- indemnización por despido sin justa causa (art. 64 CST)
    if motivo == "Despido sin justa causa":
        indem, detalle = _indemnizacion(
            tipo_contrato, liq.dias_totales, salario_mensual, fecha_retiro, fecha_fin_pactada, smmlv)
        liq.conceptos.append(Concepto("Indemnización por despido sin justa causa", _pesos(indem), detalle))
    elif tipo_contrato != "Indefinido" and motivo == "Renuncia":
        liq.advertencias.append(
            "Renuncia en contrato fijo/obra: el trabajador no recibe indemnización y el empleador podría "
            "reclamar perjuicios según el caso. Revisa el contrato.")

    liq.advertencias.append(
        f"Valores de referencia: SMMLV {formato_pesos(smmlv)} y auxilio de transporte "
        f"{formato_pesos(auxilio_transporte)}. Verifica que estén vigentes.")
    liq.advertencias.append("Herramienta de apoyo; no reemplaza la asesoría de un abogado laboralista o contador.")
    return liq


def _indemnizacion(tipo, dias_totales, salario, fecha_retiro, fecha_fin, smmlv):
    sal_dia = salario / 30
    if tipo == "Indefinido":
        if salario < 10 * smmlv:
            primer_anio, adicional = 30, 20
        else:
            primer_anio, adicional = 20, 15
        extra = max(0, dias_totales - 360) / 360 * adicional
        dias = primer_anio + extra
        return sal_dia * dias, (
            f"{primer_anio} días + {adicional} días/año adicional (proporcional) = {dias:.2f} días × salario/30")

    if not fecha_fin:
        raise ValueError("Para contrato fijo u obra/labor indica la fecha de terminación pactada.")
    faltan = max(0, dias_360(fecha_retiro + timedelta(days=1), fecha_fin))
    if tipo == "Obra o labor":
        faltan = max(faltan, 15)
        return sal_dia * faltan, f"{faltan} días faltantes (mínimo 15) × salario/30"
    return sal_dia * faltan, f"{faltan} días faltantes del plazo × salario/30"


# ---------------------------------------------------------------- exportación a Excel
def exportar_excel(liq, ruta, datos=None):
    """Escribe la liquidación en un .xlsx con formato. `datos` (dict opcional): Trabajador,
    Tipo de contrato, Motivo, Fecha de ingreso, Fecha de retiro, Salario mensual."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Liquidación"
    formato_cop = '"$"#,##0'
    azul = PatternFill("solid", fgColor="1F4E78")
    gris = PatternFill("solid", fgColor="F2F2F2")
    borde = Border(*(Side(style="thin", color="BFBFBF"),) * 4)

    ws["A1"] = "Liquidación de contrato de trabajo"
    ws["A1"].font = Font(size=16, bold=True)
    ws.merge_cells("A1:C1")

    fila = 3
    for clave, valor in (datos or {}).items():
        ws.cell(fila, 1, clave).font = Font(bold=True)
        celda = ws.cell(fila, 2, valor)
        celda.alignment = Alignment(horizontal="left")
        if clave == "Salario mensual":
            celda.number_format = formato_cop
        fila += 1
    ws.cell(fila, 1, "Días liquidados (año de 360)").font = Font(bold=True)
    ws.cell(fila, 2, liq.dias_totales).alignment = Alignment(horizontal="left")
    fila += 1
    ws.cell(fila, 1, "Auxilio de transporte en la base").font = Font(bold=True)
    ws.cell(fila, 2, "Sí" if liq.aplica_auxilio else "No").alignment = Alignment(horizontal="left")
    fila += 2

    for col, titulo in enumerate(("Concepto", "Valor", "Detalle del cálculo"), 1):
        c = ws.cell(fila, col, titulo)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = azul
        c.border = borde
        c.alignment = Alignment(horizontal="center")
    primera = fila + 1
    for i, concepto in enumerate(liq.conceptos):
        fila += 1
        fila_celdas = (ws.cell(fila, 1, concepto.nombre), ws.cell(fila, 2, concepto.valor),
                       ws.cell(fila, 3, concepto.detalle))
        fila_celdas[1].number_format = formato_cop
        for c in fila_celdas:
            c.border = borde
            if i % 2:
                c.fill = gris
        fila_celdas[2].alignment = Alignment(wrap_text=True, vertical="top")
    ultima = fila

    fila += 1
    ws.cell(fila, 1, "TOTAL A PAGAR (bruto)")
    ws.cell(fila, 2, f"=SUM(B{primera}:B{ultima})").number_format = formato_cop
    for col in (1, 2, 3):
        c = ws.cell(fila, col)
        c.font = Font(bold=True)
        c.border = borde
        c.fill = PatternFill("solid", fgColor="DDEBF7")

    fila += 2
    for nota in liq.advertencias:
        ws.cell(fila, 1, "• " + nota).alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=3)
        ws.row_dimensions[fila].height = 32
        fila += 1

    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 20
    ws.column_dimensions["C"].width = 70
    wb.save(ruta)


# ---------------------------------------------------------------- exportación a PDF
def _monto_en_letras(valor):
    """Convierte un entero a pesos colombianos en letras."""
    try:
        from num2words import num2words
        letras = num2words(int(round(valor)), lang="es").upper()
        letras = letras.replace("UNO MILLON", "UN MILLON").replace("UNO MIL", "UN MIL")
        return f"{letras} PESOS M/CTE."
    except ImportError:
        return f"{formato_pesos(valor)} PESOS M/CTE."


def exportar_pdf(liq, ruta, datos=None):
    """Genera un PDF replicando el formato clásico de liquidación laboral colombiana."""
    import re
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    datos = datos or {}

    def fmt_fecha(f):
        if isinstance(f, str):
            try:
                f = parsear_fecha(f)
            except ValueError:
                return f
        if isinstance(f, (date, datetime)):
            meses = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                     "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
            return f"{f.day}-{meses[f.month - 1]}-{str(f.year)[2:]}"
        return ""

    def fmt_num(v, dec=0):
        if v is None or v == "":
            return ""
        if dec == 0:
            return f"{int(round(v)):,}"
        return f"{v:,.{dec}f}"

    def fmt_dinero(v):
        if not v:
            return "$ -"
        return "$ " + f"{int(round(v)):,}"

    trabajador = str(datos.get("Trabajador", "")).upper()
    if trabajador == "-":
        trabajador = ""
    cedula = str(datos.get("Cedula", ""))
    cargo = str(datos.get("Cargo", "")).upper()
    tipo_contrato = str(datos.get("Tipo de contrato", "Indefinido")).upper()
    motivo = str(datos.get("Motivo", ""))
    f_ing_raw = datos.get("Fecha de ingreso")
    f_ret_raw = datos.get("Fecha de retiro")
    f_ing_str = fmt_fecha(f_ing_raw)
    f_ret_str = fmt_fecha(f_ret_raw)

    salario = datos.get("Salario mensual", 0)
    sal_promedio = datos.get("Salario promedio", 0) or 0
    aux_trans = AUXILIO_TRANSPORTE_2026 if liq.aplica_auxilio else 0
    base_total = (sal_promedio if sal_promedio else salario) + aux_trans
    sanciones = datos.get("Sanciones dias", 0)

    empleador = str(datos.get("Empleador", "PROALUM")).upper()
    nit_empleador = str(datos.get("Nit empleador", ""))

    mapa_conceptos = {c.nombre: c for c in liq.conceptos}

    ces_obj = mapa_conceptos.get("Cesantías")
    int_obj = mapa_conceptos.get("Intereses sobre cesantías")
    pri_obj = mapa_conceptos.get("Prima de servicios")
    vac_obj = mapa_conceptos.get("Vacaciones")
    sal_pend_obj = mapa_conceptos.get("Salario pendiente")
    indem_obj = mapa_conceptos.get("Indemnización por despido sin justa causa")

    def extraer_dias(detalle, default=liq.dias_totales):
        m = re.search(r"(\d+)\s*días", detalle)
        return int(m.group(1)) if m else default

    def extraer_corte(detalle, default_str=f_ing_str):
        m = re.search(r"desde\s+(\d{4}-\d{2}-\d{2})", detalle)
        return fmt_fecha(m.group(1)) if m else default_str

    dias_ces = extraer_dias(ces_obj.detalle) if ces_obj else 0
    corte_ces = extraer_corte(ces_obj.detalle) if ces_obj else f_ing_str

    dias_pri = extraer_dias(pri_obj.detalle) if pri_obj else 0
    corte_pri = extraer_corte(pri_obj.detalle) if pri_obj else f_ing_str

    dias_vac_pend = 0.0
    if vac_obj:
        m_vac = re.search(r"([\d\.]+)\s*días hábiles pendientes", vac_obj.detalle)
        if m_vac:
            dias_vac_pend = float(m_vac.group(1))

    dias_sal_pend = extraer_dias(sal_pend_obj.detalle, 0) if sal_pend_obj else 0
    val_sal_pend = (salario / 30 * dias_sal_pend) if dias_sal_pend else 0
    val_aux_pend = (aux_trans / 30 * dias_sal_pend) if (dias_sal_pend and liq.aplica_auxilio) else 0
    horas_extras = datos.get("Horas extras", 0) or 0
    val_indem = indem_obj.valor if indem_obj else 0

    total_devengos = (
        (vac_obj.valor if vac_obj else 0)
        + (ces_obj.valor if ces_obj else 0)
        + (int_obj.valor if int_obj else 0)
        + (pri_obj.valor if pri_obj else 0)
        + _pesos(val_sal_pend)
        + _pesos(val_aux_pend)
        + _pesos(horas_extras)
        + val_indem
    )

    valor_neto = total_devengos

    doc = SimpleDocTemplate(
        ruta,
        pagesize=letter,
        leftMargin=28,
        rightMargin=28,
        topMargin=24,
        bottomMargin=24,
    )
    W = letter[0] - 56

    GRIS_BARRA = colors.HexColor("#BFBFBF")
    NEGRO = colors.black

    estilo_legal = ParagraphStyle(
        "Legal",
        fontName="Helvetica",
        fontSize=7.8,
        leading=9.5,
        textColor=NEGRO,
    )

    elementos = []

    t_titulo = Table(
        [[f"LIQUIDACION DE CONTRATO DE TRABAJO A TERMINO {tipo_contrato}"]],
        colWidths=[W],
        rowHeights=[18],
    )
    t_titulo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GRIS_BARRA),
        ("BOX", (0, 0), (-1, -1), 1.5, NEGRO),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(t_titulo)
    elementos.append(Spacer(1, 6))

    t_id = Table(
        [
            ["NOMBRE:", trabajador],
            ["C.C.:", cedula],
            ["CARGO:", cargo],
            ["CAUSA DE LA LIQUIDACION:", motivo],
        ],
        colWidths=[W * 0.42, W * 0.58],
        rowHeights=[13, 13, 13, 15],
    )
    t_id.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
        ("FONTNAME", (1, 2), (1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    t_periodo = Table(
        [
            ["PERIODO DE LIQUIDACION", ""],
            ["FECHA TERMINACION DE CONTRATO", f_ret_str],
            ["FECHA DE INICIO CONTRATO", f_ing_str],
            ["TIEMPO TOTAL LABORADO", fmt_num(liq.dias_totales)],
            ["FECHA DE INICIO LIQUIDACION PRESTACIONES\nSOCIALES", f_ing_str],
        ],
        colWidths=[W * 0.44, W * 0.14],
        rowHeights=[14, 13, 13, 13, 22],
    )
    t_periodo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GRIS_BARRA),
        ("BOX", (0, 0), (0, 0), 1, NEGRO),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (1, 1), (1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    t_sal = Table(
        [
            ["SALARIO BASE DE LIQUIDACION:", ""],
            ["SUELDO BASICO:", fmt_dinero(salario)],
            ["AUXILIO DE TRANSPORTE:", fmt_dinero(aux_trans) if liq.aplica_auxilio else ""],
            ["PROMEDIO SALARIO VARIABLE", fmt_dinero(sal_promedio) if sal_promedio else ""],
            ["TOTAL BASE DE LIQUIDACION", fmt_dinero(base_total)],
            ["SANCIONES EN DIAS", str(sanciones)],
        ],
        colWidths=[W * 0.27, W * 0.14],
        rowHeights=[13, 13, 13, 13, 14, 13],
    )
    t_sal.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.2, NEGRO),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 4), (1, 5), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("LINEABOVE", (1, 4), (1, 4), 1, NEGRO),
        ("LINEBELOW", (1, 4), (1, 4), 1, NEGRO),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (1, 0), (1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    t_mid = Table([[t_periodo, t_sal]], colWidths=[W * 0.59, W * 0.41])
    t_mid.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    def bloque_prestacion(titulo, filas, sombreado_extra=None):
        w_bloque = W * 0.485
        t = Table(
            [[titulo, ""]] + filas,
            colWidths=[w_bloque * 0.72, w_bloque * 0.28],
            rowHeights=[13] + [13] * len(filas),
        )
        estilos = [
            ("BOX", (0, 0), (-1, -1), 1.2, NEGRO),
            ("SPAN", (0, 0), (1, 0)),
            ("ALIGN", (0, 0), (1, 0), "CENTER"),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("BACKGROUND", (0, 1), (0, 1), GRIS_BARRA),
            ("BOX", (0, 1), (0, 1), 0.8, NEGRO),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (1, 1), (1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]
        if sombreado_extra is not None:
            estilos.append(("BACKGROUND", (0, sombreado_extra), (0, sombreado_extra), GRIS_BARRA))
            estilos.append(("BOX", (0, sombreado_extra), (0, sombreado_extra), 0.8, NEGRO))
        t.setStyle(TableStyle(estilos))
        return t

    b_prima = bloque_prestacion("PRIMA", [
        ["FECHA DE LIQUIDACION PRIMA", f_ret_str],
        ["FECHA DE CORTE PRIMA", corte_pri],
        ["DIAS PRIMA", fmt_num(dias_pri, 2)],
    ])
    b_cesantias = bloque_prestacion("CESANTIAS", [
        ["FECHA DE LIQUIDACION CESANTIAS", f_ret_str],
        ["FECHA DE CORTE CESANTIAS", corte_ces],
        ["DIAS CESANTIAS", fmt_num(dias_ces, 2)],
    ])
    b_vacaciones = bloque_prestacion("VACACIONES", [
        ["FECHA DE LIQUIDACION VACACIONES", f_ret_str],
        ["FECHA DE CORTE VACACIONES", f_ing_str],
        ["TOTAL DIAS DE VACACIONES", fmt_num(liq.dias_totales, 2)],
        ["DIAS TOMADOS DE VACACIONES", fmt_num(datos.get("Dias vacaciones disfrutados", 0), 0)],
        ["DIAS PENDIENTES", fmt_num(dias_vac_pend, 2)],
    ], sombreado_extra=4)
    b_intereses = bloque_prestacion("INTERESES A LAS CESANTIAS", [
        ["FECHA DE LIQUIDACION INTERESES", f_ret_str],
        ["FECHA DE CORTE INTERESES", corte_ces],
        ["DIAS INTERESES", fmt_num(dias_ces, 2)],
    ])

    t_grid_prest = Table(
        [
            [b_prima, "", b_cesantias],
            ["", "", ""],
            [b_vacaciones, "", b_intereses],
        ],
        colWidths=[W * 0.485, W * 0.03, W * 0.485],
        rowHeights=[None, 8, None],
    )
    t_grid_prest.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    t_marco_sup = Table(
        [[t_id], [t_mid], [Spacer(1, 6)], [t_grid_prest], [Spacer(1, 6)]],
        colWidths=[W],
    )
    t_marco_sup.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.5, NEGRO),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elementos.append(t_marco_sup)
    elementos.append(Spacer(1, 8))

    col_w = [W * 0.37, W * 0.11, W * 0.04, W * 0.09, W * 0.04, W * 0.09, W * 0.08, W * 0.18]

    filas_pagos = [
        ["RESUMEN LIQUIDACION PAGOS:", "", "", "", "", "", "", ""],
        ["DIAS DE VACACIONES PENDIENTES:", fmt_num(dias_vac_pend, 2), "/", fmt_num(salario), "", "30", "", fmt_dinero(vac_obj.valor if vac_obj else 0)],
        ["CESANTIAS:", fmt_num(base_total), "/", "360", "x", fmt_num(dias_ces), "", fmt_dinero(ces_obj.valor if ces_obj else 0)],
        ["INTERESES DE CESANTIAS", fmt_num(ces_obj.valor if ces_obj else 0), "/", "360", "x", fmt_num(dias_ces), "X  12%", fmt_dinero(int_obj.valor if int_obj else 0)],
        ["PRIMA SERVICIOS", fmt_num(base_total), "/", "360", "x", fmt_num(dias_pri), "", fmt_dinero(pri_obj.valor if pri_obj else 0)],
        ["SUELDO PENDIENTE POR CANCELAR:", fmt_num(salario), "/", "30", "x", fmt_num(dias_sal_pend), "", fmt_dinero(val_sal_pend)],
        ["HORAS EXTRAS PENDIENTE POR CANCELAR:", "", "", "", "", "", "", fmt_dinero(horas_extras)],
        ["AUX. TRANSP. PENDIENTE POR CANCELAR", "", "/", "30", "x", fmt_num(dias_sal_pend), "", fmt_dinero(val_aux_pend)],
    ]
    if val_indem > 0:
        filas_pagos.append(["INDEMNIZACION ART. 64 CST:", "", "", "", "", "", "", fmt_dinero(val_indem)])

    idx_tot_dev = len(filas_pagos)
    filas_pagos.append(["TOTAL DEVENGOS", "", "", "", "", "", "", fmt_dinero(total_devengos)])

    idx_val_liq = len(filas_pagos)
    filas_pagos.append(["VALOR LIQUIDACION", "", "", "", "", "", "", fmt_dinero(valor_neto)])

    idx_letras = len(filas_pagos)
    filas_pagos.append([f"LA  SUMA DE:   {_monto_en_letras(valor_neto)}", "", "", "", "", "", "", ""])

    t_resumen = Table(filas_pagos, colWidths=col_w, rowHeights=[13] * (len(filas_pagos) - 1) + [22])
    estilo_resumen = [
        ("BOX", (0, 0), (-1, -1), 1.5, NEGRO),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (1, 1), (6, -1), "RIGHT"),
        ("ALIGN", (7, 1), (7, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("BACKGROUND", (0, 0), (0, 0), GRIS_BARRA),
        ("BOX", (0, 0), (0, 0), 1, NEGRO),
        ("LINEABOVE", (0, idx_tot_dev), (-1, idx_tot_dev), 1.2, NEGRO),
        ("LINEBELOW", (0, idx_tot_dev), (-1, idx_tot_dev), 1.2, NEGRO),
        ("BOX", (7, idx_tot_dev), (7, idx_tot_dev), 1.5, NEGRO),
        ("FONTNAME", (7, idx_tot_dev), (7, idx_tot_dev), "Helvetica-Bold"),
        ("LINEABOVE", (0, idx_val_liq), (-1, idx_val_liq), 1.2, NEGRO),
        ("LINEBELOW", (0, idx_val_liq), (-1, idx_val_liq), 1.2, NEGRO),
        ("BOX", (7, idx_val_liq), (7, idx_val_liq), 1.5, NEGRO),
        ("FONTNAME", (7, idx_val_liq), (7, idx_val_liq), "Helvetica-Bold"),
        ("SPAN", (0, idx_letras), (-1, idx_letras)),
        ("BACKGROUND", (0, idx_letras), (-1, idx_letras), GRIS_BARRA),
        ("VALIGN", (0, idx_letras), (-1, idx_letras), "TOP"),
    ]
    t_resumen.setStyle(TableStyle(estilo_resumen))
    elementos.append(t_resumen)

    p1 = Paragraph(
        "1. Que el patrono ha incorporado en la presente liquidación los importes correspondientes a salarios, "
        "horas extras, descansos compensatorios, cesantías, vacaciones, prima de servicios, auxilio de transporte, "
        "y en sí, todo concepto relacionado con salarios, prestaciones o indemnizaciones causadas al quedar "
        "extinguido el contrato de trabajo.",
        estilo_legal,
    )
    p2 = Paragraph(
        f"2. Que con el pago del dinero anotado en la presente liquidación, queda transada cualquier diferencia "
        f"relativa al contrato de trabajo extinguido, o a cualquier diferencia anterior. Por lo tanto, esta "
        f"transacción tiene como efecto la terminación de las obligaciones provenientes de la relación laboral "
        f"que existió entre <b>{empleador}</b> y el trabajador, quienes declaran estar a paz y salvo por todo concepto.",
        estilo_legal,
    )

    t_firmas = Table(
        [
            ["", "", ""],
            ["EL EMPLEADO", "", "EL EMPLEADOR"],
            [f"C.C. {cedula}", "", f"NIT. {nit_empleador}" if nit_empleador else ""],
        ],
        colWidths=[W * 0.42, W * 0.30, W * 0.28],
        rowHeights=[45, 13, 13],
    )
    t_firmas.setStyle(TableStyle([
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("LINEABOVE", (0, 1), (0, 1), 1.2, NEGRO),
        ("LINEABOVE", (2, 1), (2, 1), 1.2, NEGRO),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))

    t_pie = Table(
        [
            ["SE HACE CONSTAR:"],
            [p1],
            [p2],
            [t_firmas],
        ],
        colWidths=[W],
        rowHeights=[20, None, None, None],
    )
    t_pie.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.5, NEGRO),
        ("LINEBELOW", (0, 0), (0, 2), 1, NEGRO),
        ("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (0, 0), 8),
        ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 1), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
    ]))
    elementos.append(t_pie)

    doc.build(elementos)
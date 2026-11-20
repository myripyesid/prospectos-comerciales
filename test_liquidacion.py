"""Pruebas de liquidacion.py. Ejecutar: python test_liquidacion.py"""
from datetime import date
from liquidacion import calcular_liquidacion, dias_360, SMMLV_2026, AUXILIO_TRANSPORTE_2026


def valor(liq, nombre):
    return next(c.valor for c in liq.conceptos if c.nombre.startswith(nombre))


def test_dias_360():
    assert dias_360(date(2026, 1, 1), date(2026, 6, 30)) == 180
    assert dias_360(date(2026, 1, 1), date(2026, 12, 31)) == 360
    assert dias_360(date(2026, 1, 1), date(2026, 2, 28)) == 60   # febrero cuenta 30
    assert dias_360(date(2026, 3, 10), date(2026, 3, 10)) == 1


def test_medio_ano_con_auxilio():
    liq = calcular_liquidacion(date(2026, 1, 1), date(2026, 6, 30), SMMLV_2026)
    base = SMMLV_2026 + AUXILIO_TRANSPORTE_2026  # 2.000.000
    assert liq.aplica_auxilio
    assert valor(liq, "Cesantías") == round(base * 180 / 360)          # 1.000.000
    assert valor(liq, "Intereses") == 60_000
    assert valor(liq, "Prima") == 1_000_000
    assert valor(liq, "Vacaciones") == round(SMMLV_2026 * 180 / 720)   # sin auxilio


def test_sin_auxilio_si_gana_mas_de_2_smmlv():
    liq = calcular_liquidacion(date(2026, 1, 1), date(2026, 6, 30), 4_000_000)
    assert not liq.aplica_auxilio
    assert valor(liq, "Cesantías") == 2_000_000


def test_indemnizacion_indefinido_menos_de_10_smmlv():
    # 2,5 años (900 días): 30 + 20*(540/360)=60 días
    liq = calcular_liquidacion(date(2024, 1, 1), date(2026, 6, 30), 2_000_000,
                               motivo="Despido sin justa causa")
    assert liq.dias_totales == 900
    assert valor(liq, "Indemnización") == 4_000_000


def test_indemnizacion_menos_de_un_ano():
    liq = calcular_liquidacion(date(2026, 1, 1), date(2026, 6, 30), 3_000_000,
                               motivo="Despido sin justa causa")
    assert valor(liq, "Indemnización") == 3_000_000  # 30 días


def test_indemnizacion_10_smmlv_o_mas():
    sal = 10 * SMMLV_2026
    liq = calcular_liquidacion(date(2024, 1, 1), date(2026, 6, 30), sal,
                               motivo="Despido sin justa causa")
    # 20 + 15*1,5 = 42,5 días
    assert valor(liq, "Indemnización") == round(sal / 30 * 42.5)


def test_indemnizacion_fijo_tiempo_faltante():
    liq = calcular_liquidacion(date(2026, 1, 1), date(2026, 3, 31), 3_000_000,
                               tipo_contrato="Fijo", motivo="Despido sin justa causa",
                               fecha_fin_pactada=date(2026, 12, 31))
    assert valor(liq, "Indemnización") == 3_000_000 * 9  # abr-dic = 270 días


def test_obra_labor_minimo_15_dias():
    liq = calcular_liquidacion(date(2026, 1, 1), date(2026, 3, 31), 3_000_000,
                               tipo_contrato="Obra o labor", motivo="Despido sin justa causa",
                               fecha_fin_pactada=date(2026, 4, 5))
    assert valor(liq, "Indemnización") == 1_500_000  # mínimo 15 días


def test_sin_indemnizacion_si_renuncia():
    liq = calcular_liquidacion(date(2024, 1, 1), date(2026, 6, 30), 2_000_000)
    assert not any(c.nombre.startswith("Indemnización") for c in liq.conceptos)


def test_vacaciones_disfrutadas_y_salario_pendiente():
    liq = calcular_liquidacion(date(2025, 1, 1), date(2025, 12, 31), 4_000_000,
                               dias_vacaciones_disfrutados=15, dias_salario_pendiente=10)
    assert valor(liq, "Vacaciones") == 0
    assert valor(liq, "Salario pendiente") == 1_333_333  # sin auxilio (gana > 2 SMMLV)
    liq2 = calcular_liquidacion(date(2025, 1, 1), date(2025, 12, 31), 3_000_000, dias_salario_pendiente=10)
    assert valor(liq2, "Salario pendiente") == round(3_000_000 / 30 * 10 + AUXILIO_TRANSPORTE_2026 / 30 * 10)


if __name__ == "__main__":
    for nombre, fn in list(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)

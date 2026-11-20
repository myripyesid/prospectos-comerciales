"""Pruebas del cálculo y PDF de cotizaciones."""
import os
import tempfile
import unittest

import cotizaciones
from openpyxl import load_workbook


class PruebasCotizaciones(unittest.TestCase):
    def crear_cotizacion(self, items=None, **cambios):
        datos = {
            "cliente": "Comercial Ejemplo",
            "nit": "900123456-7",
            "direccion": "Calle 10 # 20-30",
            "telefono": "3001234567",
            "fecha": "2026-11-20",
            "numero": "205",
            "items": items if items is not None else [{
                "cantidad": "1",
                "descripcion": "Vitrina 1.60 x 0.55",
                "valor_unitario": "790.000",
            }],
            "fecha_entrega": "12 días hábiles",
            "garantia": "2 años en ajustes",
        }
        datos.update(cambios)
        return cotizaciones.calcular_cotizacion(**datos)

    def test_calcula_total_de_varios_productos(self):
        cotizacion = self.crear_cotizacion(items=[
            {"cantidad": "1", "descripcion": "Vitrina", "valor_unitario": "790.000"},
            {"cantidad": "2", "descripcion": "Estante", "valor_unitario": "125000"},
            {"cantidad": "", "descripcion": "", "valor_unitario": ""},
        ])

        self.assertEqual(cotizacion["items"][0]["valor_total"], 790000)
        self.assertEqual(cotizacion["items"][1]["valor_total"], 250000)
        self.assertEqual(cotizacion["subtotal"], 1040000)
        self.assertEqual(cotizacion["total"], 1040000)
        self.assertEqual(cotizacion["fecha"], "20/11/2026")

    def test_rechaza_articulos_incompletos_y_valores_invalidos(self):
        with self.assertRaisesRegex(ValueError, "descripción"):
            self.crear_cotizacion(items=[
                {"cantidad": "1", "descripcion": "", "valor_unitario": "5000"}
            ])
        with self.assertRaisesRegex(ValueError, "entero"):
            cotizaciones.parsear_cantidad("1.5")
        with self.assertRaisesRegex(ValueError, "número entero"):
            cotizaciones.parsear_valor("mil pesos")

    def test_requiere_cliente_numero_producto_entrega_y_garantia(self):
        for campo, valor in (
            ("cliente", ""),
            ("numero", ""),
            ("fecha_entrega", ""),
            ("garantia", ""),
            ("items", []),
        ):
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                self.crear_cotizacion(**{campo: valor})

    def test_exporta_pdf(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "cotizacion_205.pdf")

            cotizaciones.exportar_pdf(ruta, self.crear_cotizacion())

            with open(ruta, "rb") as archivo:
                self.assertTrue(archivo.read().startswith(b"%PDF-"))

    def test_exporta_excel_con_formulas_y_total(self):
        cotizacion = self.crear_cotizacion(items=[
            {"cantidad": "1", "descripcion": "Vitrina", "valor_unitario": "790.000"},
            {"cantidad": "2", "descripcion": "Estante", "valor_unitario": "125000"},
        ])
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "cotizacion_205.xlsx")

            cotizaciones.exportar_excel(ruta, cotizacion)

            hoja = load_workbook(ruta, data_only=False)["Cotización"]
            self.assertEqual(hoja["B1"].value, "PROALUM | PROYECTOS EN VIDRIO Y ALUMINIO")
            self.assertEqual(len(hoja._images), 1)
            self.assertEqual(hoja["D11"].value, "=A11*C11")
            self.assertEqual(hoja["D12"].value, "=A12*C12")
            self.assertEqual(hoja["D13"].value, "=SUM(D11:D12)")
            self.assertEqual(hoja["D14"].value, "=D13")
            self.assertEqual(hoja["A20"].value, "GARANTÍA: 2 años en ajustes")


if __name__ == "__main__":
    unittest.main()

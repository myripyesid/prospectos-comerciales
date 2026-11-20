"""Pruebas del conteo y exportación de reportes de contactos."""
import csv
import os
import tempfile
import unittest

import reportes


class PruebasReportes(unittest.TestCase):
    def crear_csv(
        self, carpeta, filas,
        columnas=("Nombre", "Dirección", "Teléfono", "Contactado")
    ):
        ruta = os.path.join(carpeta, "contactos.csv")
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=columnas)
            escritor.writeheader()
            escritor.writerows(filas)
        return ruta

    def crear_log(self, carpeta, filas):
        ruta = os.path.join(carpeta, "whatsapp_envios.csv")
        with open(ruta, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.DictWriter(
                archivo, fieldnames=("fecha_hora", "numero", "nombre", "estado", "modo")
            )
            escritor.writeheader()
            escritor.writerows(filas)
        return ruta

    def test_cuenta_celulares_unicos_marcados_como_contactados(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_csv = self.crear_csv(carpeta, [
                {"Nombre": "Negocio 1", "Dirección": "", "Teléfono": "300 123 4567", "Contactado": "Sí"},
                {"Nombre": "Negocio repetido", "Dirección": "", "Teléfono": "+57 3001234567", "Contactado": "Sí"},
                {"Nombre": "Negocio 2", "Dirección": "", "Teléfono": "310 765 4321", "Contactado": "No"},
                {"Nombre": "Sin celular", "Dirección": "", "Teléfono": "No disponible", "Contactado": "Sí"},
            ])

            self.assertEqual(reportes.contar_contactos_csv(ruta_csv), 1)

    def test_migra_envios_existentes_a_la_columna_contactado(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_csv = self.crear_csv(carpeta, [
                {"Nombre": "Negocio", "Dirección": "", "Teléfono": "3001234567"},
            ], columnas=("Nombre", "Dirección", "Teléfono"))
            ruta_log = self.crear_log(carpeta, [
                {"numero": "573001234567", "estado": "enviado"},
            ])

            reportes.preparar_base_contactos(ruta_csv, ruta_log)

            self.assertEqual(reportes.contar_contactos_csv(ruta_csv), 1)

    def test_marca_contactado_por_numero_y_persiste_el_cambio(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta_csv = self.crear_csv(carpeta, [
                {"Nombre": "Negocio 1", "Dirección": "", "Teléfono": "300 123 4567"},
                {"Nombre": "Negocio 2", "Dirección": "", "Teléfono": "310 765 4321"},
            ])

            reportes.marcar_contactado_csv(ruta_csv, "573001234567")

            self.assertEqual(reportes.contar_contactos_csv(ruta_csv), 1)
            df = reportes.preparar_base_contactos(ruta_csv)
            self.assertEqual(df.loc[0, "Contactado"], "Sí")
            self.assertEqual(df.loc[1, "Contactado"], "No")

    def test_rechaza_csv_sin_columnas_requeridas(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = self.crear_csv(carpeta, [], columnas=("nombre", "telefono"))

            with self.assertRaisesRegex(ValueError, "Nombre.*Teléfono"):
                reportes.contar_contactos_csv(ruta)

    def test_calcula_porcentajes_y_particiones(self):
        metricas = reportes.calcular_metricas(20, 8, 3)

        self.assertEqual(metricas["porcentaje_respuesta"], 40)
        self.assertEqual(metricas["porcentaje_citas"], 15)
        self.assertEqual(metricas["sin_respuesta"], 12)
        self.assertEqual(metricas["respondieron_sin_cita"], 5)
        self.assertFalse(metricas["total_manual"])

    def test_permite_usar_total_manual_en_lugar_del_registro(self):
        metricas = reportes.calcular_metricas(12, 6, 2, total_manual=True)

        self.assertEqual(metricas["total"], 12)
        self.assertEqual(metricas["porcentaje_respuesta"], 50)
        self.assertAlmostEqual(metricas["porcentaje_citas"], 100 / 6)
        self.assertTrue(metricas["total_manual"])

        with self.assertRaisesRegex(ValueError, "no pueden superar"):
            reportes.calcular_metricas(5, 6, 1, total_manual=True)

    def test_rechaza_totales_incoherentes(self):
        for valores in ((0, 0, 0), (10, 11, 0), (10, 5, 6), (10, -1, 0), (10, 1.5, 0)):
            with self.subTest(valores=valores), self.assertRaises(ValueError):
                reportes.calcular_metricas(*valores)

    def test_exporta_pdf_con_graficos(self):
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = os.path.join(carpeta, "reporte.pdf")
            metricas = reportes.calcular_metricas(20, 8, 3)

            reportes.exportar_reporte_pdf(ruta, "Campaña manual", metricas)

            with open(ruta, "rb") as archivo:
                self.assertTrue(archivo.read().startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()

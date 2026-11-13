import os
import re
import time
import random
import threading
import urllib.parse
import webbrowser
import pandas as pd
import customtkinter as ctk
from tkinter import messagebox
from playwright.sync_api import sync_playwright

# Configuración visual global
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AppProspeccion(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ProAlum - Extractor & Prospección Maps")
        self.geometry("820x620")
        self.resizable(False, False)

        # Carpetas de salida
        self.carpeta_excel = "resultados_excel"
        self.carpeta_csv = "resultados_csv"
        os.makedirs(self.carpeta_excel, exist_ok=True)
        os.makedirs(self.carpeta_csv, exist_ok=True)

        # Variables de estado para campaña WhatsApp
        self.df_campana = pd.DataFrame()
        self.indice_actual = 0

        # Pestañas principales
        self.tabview = ctk.CTkTabview(self, width=780, height=580)
        self.tabview.pack(padx=20, pady=20)

        self.tab_scraper = self.tabview.add("1. Extractor Google Maps")
        self.tab_whatsapp = self.tabview.add("2. Asistente WhatsApp")

        self.construir_tab_scraper()
        self.construir_tab_whatsapp()

    # =========================================================================
    # PESTAÑA 1: EXTRACTOR GOOGLE MAPS
    # =========================================================================
    def construir_tab_scraper(self):
        lbl_titulo = ctk.CTkLabel(
            self.tab_scraper,
            text="Extracción de Negocios en Google Maps",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        lbl_titulo.pack(pady=(15, 5))

        lbl_sub = ctk.CTkLabel(
            self.tab_scraper,
            text="Ingresa el rubro y ubicación (Ej: Panadería en Itagüí, Restaurantes en Barbosa)",
            text_color="gray"
        )
        lbl_sub.pack(pady=(0, 15))

        frame_input = ctk.CTkFrame(self.tab_scraper, fg_color="transparent")
        frame_input.pack(pady=5)

        self.entry_busqueda = ctk.CTkEntry(
            frame_input,
            placeholder_text="Ej: Panadería en Itagüí",
            width=450,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.entry_busqueda.pack(side="left", padx=(0, 10))

        self.btn_iniciar_scraping = ctk.CTkButton(
            frame_input,
            text="Iniciar Extracción",
            width=160,
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.iniciar_hilo_scraping
        )
        self.btn_iniciar_scraping.pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(self.tab_scraper, width=620)
        self.progress_bar.pack(pady=15)
        self.progress_bar.set(0)

        self.textbox_log = ctk.CTkTextbox(self.tab_scraper, width=680, height=340, font=ctk.CTkFont(size=12))
        self.textbox_log.pack(pady=5)
        self.log("Listo para buscar. Los archivos se guardarán en 'resultados_excel' y 'resultados_csv'.")

    def log(self, mensaje):
        self.textbox_log.insert("end", mensaje + "\n")
        self.textbox_log.see("end")

    def iniciar_hilo_scraping(self):
        busqueda = self.entry_busqueda.get().strip()
        if not busqueda:
            messagebox.showwarning("Campo vacío", "Por favor ingresa una búsqueda válida.")
            return

        self.btn_iniciar_scraping.configure(state="disabled", text="Extrayendo...")
        self.textbox_log.delete("1.0", "end")
        self.progress_bar.set(0.05)

        # Ejecutar Playwright en un hilo separado para no congelar la interfaz
        hilo = threading.Thread(target=self.ejecutar_scraping, args=(busqueda,), daemon=True)
        hilo.start()

    def ejecutar_scraping(self, busqueda):
        resultados = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                page = browser.new_page()

                self.after(0, self.log, f"Buscando: '{busqueda}'...")
                url_busqueda = f"https://www.google.com/maps/search/{urllib.parse.quote(busqueda)}"
                page.goto(url_busqueda)

                # 1. Manejar posible pantalla de consentimiento de cookies de Google
                try:
                    btn_cookies = page.locator('button:has-text("Aceptar todo"), button:has-text("Accept all")')
                    if btn_cookies.first.is_visible(timeout=3000):
                        btn_cookies.first.click()
                        self.after(0, self.log, "Banner de cookies aceptado.")
                except Exception:
                    pass

                # 2. Esperar a que aparezca la lista de resultados O una ficha única directa
                try:
                    page.wait_for_selector('div[role="feed"], h1.DUwDvf', timeout=20000)
                except Exception:
                    self.after(0, self.log, "No se encontraron resultados o la página tardó demasiado en responder.")
                    browser.close()
                    return

                urls_unicas = []

                # Caso A: Apareció la lista lateral con múltiples negocios
                if page.locator('div[role="feed"]').count() > 0:
                    panel_resultados = page.locator('div[role="feed"]')
                    self.after(0, self.log, "Haciendo scroll para cargar todos los negocios...")
                    
                    intentos_sin_cambio = 0
                    conteo_anterior = 0

                    while True:
                        panel_resultados.evaluate("el => el.scrollBy(0, 3000)")
                        time.sleep(random.uniform(2.0, 3.8))

                        if page.locator("text=Has llegado al final de la lista").is_visible() or \
                           page.locator("text=You've reached the end of the list").is_visible():
                            break

                        # Seguro adicional: si tras 3 scrolls no aparecen nuevos locales, detener
                        conteo_actual = page.locator('a[href*="/maps/place/"]').count()
                        if conteo_actual == conteo_anterior:
                            intentos_sin_cambio += 1
                            if intentos_sin_cambio >= 3:
                                break
                        else:
                            intentos_sin_cambio = 0
                        conteo_anterior = conteo_actual

                    enlaces = page.locator('a[href*="/maps/place/"]').all()
                    urls_unicas = list(dict.fromkeys([e.get_attribute("href") for e in enlaces]))

                # Caso B: Google Maps abrió directamente la única joyería del municipio
                elif page.locator('h1.DUwDvf').count() > 0:
                    self.after(0, self.log, "Se encontró un único resultado directo en el mapa.")
                    urls_unicas = [page.url]

                total = len(urls_unicas)
                self.after(0, self.log, f"Total a extraer: {total} negocio(s).\n")

                for idx, url in enumerate(urls_unicas, 1):
                    try:
                        if page.url != url:
                            page.goto(url)
                        page.wait_for_selector('h1', timeout=10000)

                        nombre = page.locator('h1').first.inner_text()
                        dir_el = page.locator('button[data-item-id="address"]')
                        direccion = dir_el.inner_text().replace('\n', ' ').strip() if dir_el.count() > 0 else "No disponible"

                        tel_el = page.locator('button[data-item-id*="phone:tel:"]')
                        telefono = tel_el.inner_text().replace('\n', ' ').strip() if tel_el.count() > 0 else "No disponible"

                        resultados.append({
                            "Nombre": nombre,
                            "Dirección": direccion,
                            "Teléfono": telefono
                        })

                        progreso = idx / total
                        self.after(0, self.progress_bar.set, progreso)
                        self.after(0, self.log, f"[{idx}/{total}] {nombre} | {telefono}")

                        if total > 1:
                            time.sleep(random.uniform(2.2, 4.5))
                    except Exception as e:
                        self.after(0, self.log, f"[!] Error en negocio {idx}: {e}")

                browser.close()

            if resultados:
                df = pd.DataFrame(resultados)
                nombre_archivo = re.sub(r'[^\w\s-]', '', busqueda).strip().replace(" ", "_").lower()

                df_con = df[df["Teléfono"] != "No disponible"]
                df_sin = df[df["Teléfono"] == "No disponible"]

                ruta_excel = os.path.join(self.carpeta_excel, f"{nombre_archivo}.xlsx")
                with pd.ExcelWriter(ruta_excel, engine="openpyxl") as writer:
                    df_con.to_excel(writer, sheet_name="Con Teléfono", index=False)
                    df_sin.to_excel(writer, sheet_name="Sin Teléfono", index=False)

                ruta_csv_con = os.path.join(self.carpeta_csv, f"{nombre_archivo}_con_telefono.csv")
                ruta_csv_sin = os.path.join(self.carpeta_csv, f"{nombre_archivo}_sin_telefono.csv")
                df_con.to_csv(ruta_csv_con, index=False, encoding="utf-8-sig")
                df_sin.to_csv(ruta_csv_sin, index=False, encoding="utf-8-sig")

                self.after(0, self.log, f"\n¡FINALIZADO! Total: {len(df)} | Con teléfono: {len(df_con)} | Sin teléfono: {len(df_sin)}")
                self.after(0, self.actualizar_lista_csv)
            else:
                self.after(0, self.log, "\nNo se encontraron resultados para esta búsqueda.")

        except Exception as e:
            self.after(0, self.log, f"\nError crítico: {e}")
        finally:
            self.after(0, lambda: self.btn_iniciar_scraping.configure(state="normal", text="Iniciar Extracción"))
    # =========================================================================
    # PESTAÑA 2: ASISTENTE WHATSAPP ANTI-SPAM
    # =========================================================================
    def construir_tab_whatsapp(self):
        lbl_titulo = ctk.CTkLabel(
            self.tab_whatsapp,
            text="Prospección Semi-Automática por WhatsApp",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        lbl_titulo.pack(pady=(10, 10))

        # Selección de archivo y municipio
        frame_config = ctk.CTkFrame(self.tab_whatsapp)
        frame_config.pack(fill="x", padx=20, pady=5)

        self.combo_csv = ctk.CTkComboBox(frame_config, width=320, values=["Sin archivos"])
        self.combo_csv.pack(side="left", padx=10, pady=10)

        btn_refrescar = ctk.CTkButton(frame_config, text="↻", width=35, command=self.actualizar_lista_csv)
        btn_refrescar.pack(side="left", padx=(0, 10))

        self.entry_municipio = ctk.CTkEntry(frame_config, placeholder_text="Municipio (Ej: Barbosa)", width=180)
        self.entry_municipio.pack(side="left", padx=(0, 10))

        btn_cargar = ctk.CTkButton(frame_config, text="Cargar Base", width=110, command=self.cargar_base_whatsapp)
        btn_cargar.pack(side="left", padx=5)

        # Panel de información de contacto actual
        self.frame_contacto = ctk.CTkFrame(self.tab_whatsapp)
        self.frame_contacto.pack(fill="both", expand=True, padx=20, pady=15)

        self.lbl_contador = ctk.CTkLabel(
            self.frame_contacto,
            text="Carga un archivo CSV para comenzar",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#3B8ED0"
        )
        self.lbl_contador.pack(pady=(15, 5))

        self.lbl_negocio = ctk.CTkLabel(
            self.frame_contacto,
            text="Negocio: -",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        self.lbl_negocio.pack(pady=5)

        self.lbl_telefono = ctk.CTkLabel(
            self.frame_contacto,
            text="Celular: -",
            font=ctk.CTkFont(size=14)
        )
        self.lbl_telefono.pack(pady=(0, 10))

        lbl_msg = ctk.CTkLabel(self.frame_contacto, text="Mensaje generado (puedes editarlo antes de abrir):", text_color="gray")
        lbl_msg.pack(anchor="w", padx=30)

        self.textbox_mensaje = ctk.CTkTextbox(self.frame_contacto, width=660, height=130, font=ctk.CTkFont(size=13))
        self.textbox_mensaje.pack(pady=5)

        # Botones de acción
        frame_botones = ctk.CTkFrame(self.frame_contacto, fg_color="transparent")
        frame_botones.pack(pady=15)

        self.btn_regenerar = ctk.CTkButton(
            frame_botones,
            text="Variar Texto (Spintax)",
            fg_color="gray30",
            hover_color="gray40",
            command=self.mostrar_contacto_actual,
            state="disabled"
        )
        self.btn_regenerar.pack(side="left", padx=10)

        self.btn_abrir_wa = ctk.CTkButton(
            frame_botones,
            text="Abrir Chat en WhatsApp ↗",
            fg_color="#25D366",
            hover_color="#1DA851",
            text_color="black",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.abrir_whatsapp_actual,
            state="disabled"
        )
        self.btn_abrir_wa.pack(side="left", padx=10)

        self.btn_siguiente = ctk.CTkButton(
            frame_botones,
            text="Siguiente Negocio →",
            command=self.siguiente_contacto,
            state="disabled"
        )
        self.btn_siguiente.pack(side="left", padx=10)

        self.actualizar_lista_csv()

    def actualizar_lista_csv(self):
        archivos = [f for f in os.listdir(self.carpeta_csv) if f.endswith("_con_telefono.csv")]
        if archivos:
            self.combo_csv.configure(values=archivos)
            self.combo_csv.set(archivos[0])
        else:
            self.combo_csv.configure(values=["No hay CSVs disponibles"])
            self.combo_csv.set("No hay CSVs disponibles")

    def limpiar_celular_colombia(self, telefono):
        digitos = re.sub(r'\D', '', str(telefono))
        if digitos.startswith('57') and len(digitos) == 12:
            digitos = digitos[2:]
        if len(digitos) == 10 and digitos.startswith('3'):
            return f"57{digitos}"
        return None

    def generar_spintax(self, nombre_negocio, municipio):
        saludos = ["Hola, ¿cómo están?", "Hola, buen día.", "Buenas tardes, ¿cómo les va?", "Hola, un saludo."]
        intro = [
            f"Les escribo a *{nombre_negocio}*",
            f"Me comunico con *{nombre_negocio}*",
            f"Vi a *{nombre_negocio}* en Maps y les escribo"
        ]
        cuerpo = [
            f"porque estamos apoyando varios negocios en {municipio} con renovación de exhibición y mobiliario comercial.",
            f"ya que trabajamos con locales en {municipio} fabricando vitrinas y exhibidores a medida.",
            f"porque estamos asesorando comercios en {municipio} en temas de exhibición y vitrinas."
        ]
        cierre = [
            "¿Por este medio me pueden comunicar con el encargado o administrador? Gracias.",
            "¿Será que por acá puedo hablar con la persona encargada? Muchas gracias.",
            "¿Me podrían indicar si este es el contacto del administrador? Quedo atento, gracias."
        ]
        return f"{random.choice(saludos)} {random.choice(intro)} {random.choice(cuerpo)} {random.choice(cierre)}"

    def cargar_base_whatsapp(self):
        archivo = self.combo_csv.get()
        municipio = self.entry_municipio.get().strip()

        if not archivo or archivo == "No hay CSVs disponibles":
            messagebox.showerror("Error", "Selecciona un archivo CSV válido.")
            return
        if not municipio:
            messagebox.showwarning("Falta dato", "Escribe el nombre del municipio para personalizar el mensaje.")
            return

        ruta = os.path.join(self.carpeta_csv, archivo)
        df = pd.read_csv(ruta)
        df['Celular_Limpio'] = df['Teléfono'].apply(self.limpiar_celular_colombia)

        # Guardar fijos aparte
        fijos = df[df['Celular_Limpio'].isna()]
        if not fijos.empty:
            fijos.to_csv(os.path.join(self.carpeta_csv, "fijos_para_llamar.csv"), index=False, encoding="utf-8-sig")

        self.df_campana = df.dropna(subset=['Celular_Limpio']).reset_index(drop=True)
        self.indice_actual = 0

        if self.df_campana.empty:
            messagebox.showinfo("Sin celulares", "Este archivo solo contiene teléfonos fijos (guardados en fijos_para_llamar.csv).")
            return

        self.btn_regenerar.configure(state="normal")
        self.btn_abrir_wa.configure(state="normal")
        self.btn_siguiente.configure(state="normal")
        self.mostrar_contacto_actual()

    def mostrar_contacto_actual(self):
        if self.indice_actual >= len(self.df_campana):
            messagebox.showinfo("Campaña completada", "Has recorrido todos los celulares de esta lista.")
            return

        fila = self.df_campana.iloc[self.indice_actual]
        nombre = fila['Nombre']
        numero = fila['Celular_Limpio']
        municipio = self.entry_municipio.get().strip()

        self.lbl_contador.configure(text=f"Contacto {self.indice_actual + 1} de {len(self.df_campana)}")
        self.lbl_negocio.configure(text=nombre)
        self.lbl_telefono.configure(text=f"Celular: +{numero}")

        mensaje = self.generar_spintax(nombre, municipio)
        self.textbox_mensaje.delete("1.0", "end")
        self.textbox_mensaje.insert("1.0", mensaje)

    def abrir_whatsapp_actual(self):
        fila = self.df_campana.iloc[self.indice_actual]
        numero = fila['Celular_Limpio']
        mensaje = self.textbox_mensaje.get("1.0", "end").strip()

        texto_codificado = urllib.parse.quote(mensaje)
        url_wa = f"https://web.whatsapp.com/send?phone={numero}&text={texto_codificado}"
        webbrowser.open(url_wa)

    def siguiente_contacto(self):
        self.indice_actual += 1
        if self.indice_actual < len(self.df_campana):
            self.mostrar_contacto_actual()
        else:
            self.lbl_contador.configure(text="¡Lista finalizada!")
            self.btn_abrir_wa.configure(state="disabled")
            self.btn_siguiente.configure(state="disabled")


if __name__ == "__main__":
    app = AppProspeccion()
    app.mainloop()

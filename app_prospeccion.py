import os
import re
import time
import random
import threading
import urllib.parse
import webbrowser
from datetime import datetime
import pandas as pd
import customtkinter as ctk
from tkinter import messagebox, filedialog
import csv
import liquidacion as liq_mod
import reportes as reportes_mod
import cotizaciones as cot_mod
from playwright.sync_api import sync_playwright
from whatsapp_bot import BotWhatsApp

# Configuración visual global
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class AppProspeccion(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("ProAlum - Extractor & Prospección Maps")
        self.geometry("820x860")
        self.resizable(False, False)

        # Carpetas de salida
        self.carpeta_excel = "resultados_excel"
        self.carpeta_csv = "resultados_csv"
        self.carpeta_cotizaciones = "cotizaciones"
        os.makedirs(self.carpeta_excel, exist_ok=True)
        os.makedirs(self.carpeta_csv, exist_ok=True)
        os.makedirs(self.carpeta_cotizaciones, exist_ok=True)

        # Variables de estado para campaña WhatsApp
        self.df_campana = pd.DataFrame()
        self.indice_actual = 0

        # Pestañas principales
        self.tabview = ctk.CTkTabview(self, width=780, height=820)
        self.tabview.pack(padx=20, pady=20)

        self.tab_scraper = self.tabview.add("1. Extractor Google Maps")
        self.tab_whatsapp = self.tabview.add("2. Asistente WhatsApp")
        self.tab_liquidacion = self.tabview.add("3. Liquidación")
        self.tab_reportes = self.tabview.add("4. Reportes")
        self.tab_cotizaciones = self.tabview.add("5. Cotizaciones")

        self.construir_tab_scraper()
        self.construir_tab_whatsapp()
        self.construir_tab_liquidacion()
        self.construir_tab_reportes()
        self.construir_tab_cotizaciones()

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
                df["Contactado"] = "No"
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

        self.construir_panel_bot()
        self.actualizar_lista_csv()

    # -------------------------------------------------------------------------
    # BOT AUTOMÁTICO (Chromium + WhatsApp Web)
    # -------------------------------------------------------------------------
    def construir_panel_bot(self):
        self.bot = None
        frame = ctk.CTkFrame(self.tab_whatsapp)
        frame.pack(fill="x", padx=20, pady=(0, 10))

        fila1 = ctk.CTkFrame(frame, fg_color="transparent")
        fila1.pack(fill="x", padx=10, pady=(10, 4))

        ctk.CTkLabel(fila1, text="Bot:", font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 8))
        self.seg_modo = ctk.CTkSegmentedButton(
            fila1, values=["Manual (yo envío)", "Automático"], command=self.cambiar_modo_bot
        )
        self.seg_modo.set("Manual (yo envío)")
        self.seg_modo.pack(side="left", padx=(0, 15))

        self.btn_bot_inicio = ctk.CTkButton(fila1, text="▶ Iniciar", width=90, command=self.iniciar_bot)
        self.btn_bot_inicio.pack(side="left", padx=3)
        self.btn_bot_pausa = ctk.CTkButton(fila1, text="⏸ Pausa", width=90, fg_color="gray30",
                                           command=self.pausar_bot, state="disabled")
        self.btn_bot_pausa.pack(side="left", padx=3)
        self.btn_bot_stop = ctk.CTkButton(fila1, text="■ Detener", width=90, fg_color="#B03A3A",
                                          hover_color="#8A2C2C", command=self.detener_bot, state="disabled")
        self.btn_bot_stop.pack(side="left", padx=3)
        self.btn_bot_web = ctk.CTkButton(fila1, text="🌐 Abrir WhatsApp Web", width=150, fg_color="#25D366",
                                         hover_color="#1DA851", text_color="black",
                                         command=self.abrir_whatsapp_web)
        self.btn_bot_web.pack(side="right", padx=3)

        fila2 = ctk.CTkFrame(frame, fg_color="transparent")
        fila2.pack(fill="x", padx=10, pady=4)
        ctk.CTkLabel(fila2, text="Máx/día:").pack(side="left")
        self.entry_max_dia = ctk.CTkEntry(fila2, width=50)
        self.entry_max_dia.insert(0, "20")
        self.entry_max_dia.pack(side="left", padx=(4, 12))
        ctk.CTkLabel(fila2, text="Horario:").pack(side="left")
        self.entry_h_ini = ctk.CTkEntry(fila2, width=40)
        self.entry_h_ini.insert(0, "8")
        self.entry_h_ini.pack(side="left", padx=4)
        ctk.CTkLabel(fila2, text="a").pack(side="left")
        self.entry_h_fin = ctk.CTkEntry(fila2, width=40)
        self.entry_h_fin.insert(0, "18")
        self.entry_h_fin.pack(side="left", padx=4)
        self.lbl_bot_prog = ctk.CTkLabel(fila2, text="", text_color="#3B8ED0")
        self.lbl_bot_prog.pack(side="right")

        self.log_bot = ctk.CTkTextbox(frame, height=110, font=ctk.CTkFont(size=12))
        self.log_bot.pack(fill="x", padx=10, pady=(4, 10))

    def _log_bot(self, texto):
        def _w():
            self.log_bot.insert("end", f"{time.strftime('%H:%M:%S')}  {texto}\n")
            self.log_bot.see("end")
        self.after(0, _w)

    def _modo_actual(self):
        return "auto" if self.seg_modo.get() == "Automático" else "manual"

    def cambiar_modo_bot(self, _valor=None):
        if self.bot:
            self.bot.modo = self._modo_actual()
            self._log_bot(f"Modo cambiado a: {self.bot.modo}")

    def abrir_whatsapp_web(self):
        """Abre WhatsApp Web en Chromium (mismo perfil wa_profile) sin iniciar el bot."""
        if self.bot and self.bot.activo:
            messagebox.showinfo("Bot activo", "El bot ya tiene WhatsApp Web abierto. Detenlo primero si quieres abrirlo aparte.")
            return
        if getattr(self, "hilo_web", None) and self.hilo_web.is_alive():
            messagebox.showinfo("Ya abierto", "WhatsApp Web ya está abierto en Chromium.")
            return
        self.btn_bot_web.configure(state="disabled")
        self.hilo_web = threading.Thread(target=self._run_whatsapp_web, daemon=True)
        self.hilo_web.start()

    def _run_whatsapp_web(self):
        try:
            with sync_playwright() as p:
                ctx = p.chromium.launch_persistent_context(
                    os.path.abspath("wa_profile"), headless=False, viewport=None,
                    args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
                )
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
                self._log_bot("WhatsApp Web abierto. Cierra la ventana de Chromium cuando termines.")
                try:
                    while ctx.pages:           # termina cuando cierras todas las ventanas
                        ctx.pages[0].wait_for_timeout(500)
                except Exception:
                    pass
                try:
                    ctx.close()
                except Exception:
                    pass
        except Exception as e:
            self._log_bot(f"⛔ No se pudo abrir WhatsApp Web: {e}")
        finally:
            self.after(0, lambda: self.btn_bot_web.configure(state="normal"))

    def iniciar_bot(self):
        if getattr(self, "hilo_web", None) and self.hilo_web.is_alive():
            messagebox.showinfo("WhatsApp Web abierto", "Cierra la ventana de Chromium que abriste a mano antes de iniciar el bot (comparten sesión).")
            return
        if self.df_campana.empty:
            messagebox.showwarning("Sin base", "Primero carga una base con 'Cargar Base'.")
            return
        if self.bot and self.bot.activo:
            return
        try:
            cfg = {
                "max_por_dia": int(self.entry_max_dia.get()),
                "hora_inicio": int(self.entry_h_ini.get()),
                "hora_fin": int(self.entry_h_fin.get()),
            }
        except ValueError:
            messagebox.showerror("Error", "Máx/día y horario deben ser números enteros.")
            return

        municipio = self.entry_municipio.get().strip()
        contactos = [(r["Nombre"], r["Celular_Limpio"]) for _, r in self.df_campana.iterrows()]
        ruta_csv_campana = self.ruta_csv_campana
        self.bot = BotWhatsApp(
            contactos=contactos,
            generar_mensaje=lambda nombre: self.generar_spintax(nombre, municipio),
            ruta_log=os.path.join(self.carpeta_csv, "whatsapp_envios.csv"),
            perfil_dir=os.path.abspath("wa_profile"),
            modo=self._modo_actual(),
            config=cfg,
            on_log=self._log_bot,
            on_progreso=lambda i, n: self.after(0, lambda: self.lbl_bot_prog.configure(text=f"{i}/{n}")),
            on_contactado=lambda numero: reportes_mod.marcar_contactado_csv(ruta_csv_campana, numero),
            on_fin=lambda: self.after(0, self._bot_terminado),
        )
        self.btn_bot_inicio.configure(state="disabled")
        self.btn_bot_pausa.configure(state="normal", text="⏸ Pausa")
        self.btn_bot_stop.configure(state="normal")
        self.bot.iniciar()

    def pausar_bot(self):
        if not self.bot:
            return
        if self.bot._pausa.is_set():
            self.bot.pausar(False)
            self.btn_bot_pausa.configure(text="⏸ Pausa")
            self._log_bot("▶ Reanudado.")
        else:
            self.bot.pausar(True)
            self.btn_bot_pausa.configure(text="▶ Reanudar")

    def detener_bot(self):
        if self.bot:
            self.bot.detener()
            self._log_bot("Deteniendo (termina la acción en curso)...")

    def _bot_terminado(self):
        self.btn_bot_inicio.configure(state="normal")
        self.btn_bot_pausa.configure(state="disabled", text="⏸ Pausa")
        self.btn_bot_stop.configure(state="disabled")

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
        ruta_log = os.path.join(self.carpeta_csv, "whatsapp_envios.csv")
        self.df_campana = pd.DataFrame()
        self.btn_regenerar.configure(state="disabled")
        self.btn_abrir_wa.configure(state="disabled")
        self.btn_siguiente.configure(state="disabled")
        try:
            df = reportes_mod.preparar_base_contactos(ruta, ruta_log)
        except (OSError, UnicodeError, csv.Error, ValueError, pd.errors.ParserError) as error:
            messagebox.showerror("Error al cargar base", str(error))
            return
        self.ruta_csv_campana = ruta
        df['Celular_Limpio'] = df['Teléfono'].apply(self.limpiar_celular_colombia)

        # Guardar fijos aparte
        fijos = df[df['Celular_Limpio'].isna()]
        if not fijos.empty:
            fijos.to_csv(os.path.join(self.carpeta_csv, "fijos_para_llamar.csv"), index=False, encoding="utf-8-sig")

        df_con_celular = df.dropna(subset=['Celular_Limpio'])
        self.df_campana = df_con_celular[df_con_celular["Contactado"] != "Sí"].reset_index(drop=True)
        self.indice_actual = 0

        if df_con_celular.empty:
            messagebox.showinfo("Sin celulares", "Este archivo solo contiene teléfonos fijos (guardados en fijos_para_llamar.csv).")
            return
        if self.df_campana.empty:
            messagebox.showinfo("Base completada", "Todos los celulares de esta base ya figuran como contactados.")
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

        self.btn_abrir_wa.configure(state="normal")
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
        if not webbrowser.open(url_wa):
            messagebox.showerror("Error", "No se pudo abrir WhatsApp Web.")
            return
        try:
            reportes_mod.marcar_contactado_csv(self.ruta_csv_campana, numero)
        except (OSError, UnicodeError, ValueError) as error:
            messagebox.showerror("No se pudo guardar el contacto", str(error))
            return
        self.df_campana.loc[
            self.df_campana["Celular_Limpio"] == numero, "Contactado"
        ] = "Sí"
        self.btn_abrir_wa.configure(state="disabled")

    def siguiente_contacto(self):
        self.indice_actual += 1
        if self.indice_actual < len(self.df_campana):
            self.mostrar_contacto_actual()
        else:
            self.lbl_contador.configure(text="¡Lista finalizada!")
            self.btn_abrir_wa.configure(state="disabled")
            self.btn_siguiente.configure(state="disabled")

    # =========================================================================
    # PESTAÑA 4: REPORTES DE CONTACTOS
    # =========================================================================
    def construir_tab_reportes(self):
        cont = ctk.CTkScrollableFrame(self.tab_reportes)
        cont.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(
            cont,
            text="Reporte de contactos",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(15, 5))
        ctk.CTkLabel(
            cont,
            text="El total incluye celulares del CSV con estado 'enviado' en el registro de WhatsApp.",
            text_color="gray",
            wraplength=650
        ).pack(pady=(0, 15))

        selector = ctk.CTkFrame(cont)
        selector.pack(fill="x", padx=20, pady=5)
        self.combo_reporte_csv = ctk.CTkComboBox(
            selector, width=480, state="readonly",
            command=lambda _valor: self.actualizar_total_reporte()
        )
        self.combo_reporte_csv.pack(side="left", padx=10, pady=10)
        ctk.CTkButton(
            selector, text="↻", width=40,
            command=self.actualizar_lista_reportes
        ).pack(side="left", padx=(0, 10))

        self.lbl_total_reporte = ctk.CTkLabel(
            cont, text="Contactos enviados: 0",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#3B8ED0"
        )
        self.lbl_total_reporte.pack(pady=(15, 10))

        form = ctk.CTkFrame(cont)
        form.pack(fill="x", padx=20, pady=5)
        form.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkLabel(form, text="Nombre de la base (opcional):").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(15, 4)
        )
        self.entry_reporte_nombre = ctk.CTkEntry(
            form, placeholder_text="Vacío = usar el nombre del CSV"
        )
        self.entry_reporte_nombre.grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 12)
        )
        ctk.CTkLabel(form, text="Contactos hablados manualmente (opcional):").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=15, pady=(4, 4)
        )
        self.entry_reporte_contactados = ctk.CTkEntry(
            form, placeholder_text="Vacío = usar total del registro de WhatsApp"
        )
        self.entry_reporte_contactados.grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 12)
        )
        self.entry_reporte_contactados.bind("<KeyRelease>", self.actualizar_vista_reporte)
        ctk.CTkLabel(form, text="Personas que respondieron:").grid(
            row=4, column=0, sticky="w", padx=15, pady=(4, 4)
        )
        ctk.CTkLabel(form, text="Citas concretadas:").grid(
            row=4, column=1, sticky="w", padx=15, pady=(4, 4)
        )
        self.entry_reporte_respuestas = ctk.CTkEntry(form, placeholder_text="0")
        self.entry_reporte_respuestas.insert(0, "0")
        self.entry_reporte_respuestas.grid(row=5, column=0, sticky="ew", padx=15, pady=(0, 15))
        self.entry_reporte_citas = ctk.CTkEntry(form, placeholder_text="0")
        self.entry_reporte_citas.insert(0, "0")
        self.entry_reporte_citas.grid(row=5, column=1, sticky="ew", padx=15, pady=(0, 15))
        self.entry_reporte_respuestas.bind("<KeyRelease>", self.actualizar_vista_reporte)
        self.entry_reporte_citas.bind("<KeyRelease>", self.actualizar_vista_reporte)

        self.lbl_vista_reporte = ctk.CTkLabel(
            cont, text="Respuesta: 0.0%  |  Citas: 0.0%",
            font=ctk.CTkFont(size=14), wraplength=650
        )
        self.lbl_vista_reporte.pack(pady=15)
        ctk.CTkLabel(
            cont,
            text="El PDF incluye gráficos de barras y pastel con los resultados.",
            text_color="gray"
        ).pack(pady=(0, 10))
        ctk.CTkButton(
            cont, text="Exportar reporte en PDF", height=40,
            fg_color="#B03A3A", hover_color="#8A2C2C",
            command=self.exportar_reporte_contactos_pdf
        ).pack(pady=10)

        self.actualizar_lista_reportes()

    def actualizar_lista_reportes(self):
        excluidos = {
            "whatsapp_envios.csv", "asistente_whatsapp.csv",
            "fijos_para_llamar.csv", "telefonos_fijos_para_llamar.csv",
        }
        archivos = sorted(
            nombre for nombre in os.listdir(self.carpeta_csv)
            if nombre.lower().endswith(".csv")
            and nombre.lower() not in excluidos
            and not nombre.lower().endswith("_sin_telefono.csv")
        )
        if not archivos:
            self.combo_reporte_csv.configure(values=["No hay CSVs disponibles"])
            self.combo_reporte_csv.set("No hay CSVs disponibles")
            self.reporte_total_contactos = 0
            self.lbl_total_reporte.configure(text="Contactos enviados: 0")
            self.actualizar_vista_reporte()
            return

        self.combo_reporte_csv.configure(values=archivos)
        self.combo_reporte_csv.set(archivos[0])
        self.actualizar_total_reporte()

    def actualizar_total_reporte(self):
        archivo = self.combo_reporte_csv.get()
        if not archivo or archivo == "No hay CSVs disponibles":
            self.reporte_total_contactos = 0
            self.lbl_total_reporte.configure(text="Contactos enviados: 0")
            self.actualizar_vista_reporte()
            return

        ruta = os.path.join(self.carpeta_csv, archivo)
        ruta_log = os.path.join(self.carpeta_csv, "whatsapp_envios.csv")
        try:
            reportes_mod.preparar_base_contactos(ruta, ruta_log)
            self.reporte_total_contactos = reportes_mod.contar_contactos_csv(ruta)
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            self.reporte_total_contactos = 0
            self.lbl_total_reporte.configure(text="No se pudo leer el CSV o el registro de WhatsApp")
            messagebox.showerror("Error al leer CSV", str(error))
        else:
            self.lbl_total_reporte.configure(
                text=f"Contactos enviados: {self.reporte_total_contactos}"
            )
        self.actualizar_vista_reporte()

    def _calcular_metricas_reporte(self, total_registrado):
        manual = self.entry_reporte_contactados.get().strip()
        total = int(manual) if manual else total_registrado
        return reportes_mod.calcular_metricas(
            total,
            int(self.entry_reporte_respuestas.get()),
            int(self.entry_reporte_citas.get()),
            total_manual=bool(manual)
        )

    def actualizar_vista_reporte(self, _evento=None):
        try:
            metricas = self._calcular_metricas_reporte(
                getattr(self, "reporte_total_contactos", 0)
            )
        except ValueError:
            self.lbl_vista_reporte.configure(text="Revisa los totales ingresados.")
            return
        origen = "manual" if metricas["total_manual"] else "registro WhatsApp"
        self.lbl_vista_reporte.configure(
            text=(
                f"Total usado: {metricas['total']} ({origen})  |  "
                f"Respuesta: {metricas['porcentaje_respuesta']:.1f}%  |  "
                f"Citas: {metricas['porcentaje_citas']:.1f}%"
            )
        )

    def exportar_reporte_contactos_pdf(self):
        archivo = self.combo_reporte_csv.get()
        if not archivo or archivo == "No hay CSVs disponibles":
            messagebox.showwarning("Sin base", "Selecciona un CSV de contactos.")
            return

        try:
            ruta_csv = os.path.join(self.carpeta_csv, archivo)
            if self.entry_reporte_contactados.get().strip():
                if not os.path.isfile(ruta_csv):
                    raise FileNotFoundError(f"No se encontró el CSV seleccionado: {archivo}")
                total = 0
            else:
                reportes_mod.preparar_base_contactos(
                    ruta_csv,
                    os.path.join(self.carpeta_csv, "whatsapp_envios.csv")
                )
                total = reportes_mod.contar_contactos_csv(ruta_csv)
            metricas = self._calcular_metricas_reporte(total)
        except (OSError, UnicodeError, csv.Error, ValueError) as error:
            messagebox.showerror("Revisa los datos", str(error))
            return

        nombre_archivo = os.path.splitext(archivo)[0]
        nombre_base = self.entry_reporte_nombre.get().strip() or nombre_archivo
        ruta = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"reporte_contactos_{nombre_archivo}.pdf"
        )
        if not ruta:
            return
        try:
            reportes_mod.exportar_reporte_pdf(ruta, nombre_base, metricas)
        except PermissionError:
            messagebox.showerror("Error", "No se pudo guardar. ¿Tienes el archivo abierto en otro programa?")
            return
        except Exception as error:
            messagebox.showerror("Error al generar PDF", str(error))
            return
        messagebox.showinfo("Exportado", f"Reporte guardado en:\n{ruta}")

    # =========================================================================
    # PESTAÑA 5: COTIZACIONES
    # =========================================================================
    def construir_tab_cotizaciones(self):
        cont = ctk.CTkScrollableFrame(self.tab_cotizaciones)
        cont.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(
            cont, text="Generar cotización",
            font=ctk.CTkFont(size=20, weight="bold")
        ).pack(pady=(10, 5))

        datos = ctk.CTkFrame(cont)
        datos.pack(fill="x", padx=12, pady=6)
        datos.grid_columnconfigure((1, 3), weight=1)

        def campo(fila, columna, texto, atributo, placeholder="", inicial=None):
            ctk.CTkLabel(datos, text=texto, anchor="w").grid(
                row=fila * 2, column=columna * 2, sticky="w",
                padx=(10, 4), pady=(6, 2)
            )
            entrada = ctk.CTkEntry(datos, placeholder_text=placeholder)
            entrada.grid(
                row=fila * 2 + 1, column=columna * 2 + 1, sticky="ew",
                padx=(0, 10), pady=(0, 5)
            )
            if inicial:
                entrada.insert(0, inicial)
            setattr(self, atributo, entrada)

        campo(0, 0, "Cliente:", "cot_cliente", "Nombre o razón social")
        campo(0, 1, "NIT:", "cot_nit", "Opcional")
        campo(1, 0, "Dirección:", "cot_direccion", "Dirección del cliente")
        campo(1, 1, "Teléfono:", "cot_telefono", "Teléfono del cliente")
        campo(
            2, 0, "Fecha (AAAA-MM-DD):", "cot_fecha",
            inicial=datetime.now().strftime("%Y-%m-%d")
        )
        campo(2, 1, "Número de cotización:", "cot_numero", "Ej: 205")
        campo(3, 0, "Fecha o plazo de entrega:", "cot_fecha_entrega", "Ej: 12 días hábiles")
        campo(3, 1, "Garantía:", "cot_garantia", "Ej: 2 años en ajustes")

        ctk.CTkLabel(
            cont, text="Productos o servicios",
            font=ctk.CTkFont(size=15, weight="bold")
        ).pack(anchor="w", padx=15, pady=(8, 2))
        self.frame_cotizacion_items = ctk.CTkFrame(cont)
        self.frame_cotizacion_items.pack(fill="x", padx=12, pady=4)
        self.frame_cotizacion_items.grid_columnconfigure(1, weight=1)
        for columna, texto in enumerate(("CANT.", "DESCRIPCIÓN", "VALOR UNITARIO", "VALOR TOTAL", "")):
            ctk.CTkLabel(
                self.frame_cotizacion_items, text=texto,
                font=ctk.CTkFont(size=11, weight="bold")
            ).grid(row=0, column=columna, sticky="ew", padx=4, pady=5)

        self.cotizacion_items = []
        self.btn_agregar_item_cotizacion = ctk.CTkButton(
            cont, text="+ Agregar producto", width=150,
            command=self.agregar_item_cotizacion
        )
        self.btn_agregar_item_cotizacion.pack(anchor="w", padx=15, pady=5)
        self.lbl_total_cotizacion = ctk.CTkLabel(
            cont, text="TOTAL: $ 0",
            font=ctk.CTkFont(size=16, weight="bold"), text_color="#00A9DC"
        )
        self.lbl_total_cotizacion.pack(anchor="e", padx=20, pady=8)
        botones_exportacion = ctk.CTkFrame(cont, fg_color="transparent")
        botones_exportacion.pack(pady=(5, 15))
        ctk.CTkButton(
            botones_exportacion, text="Exportar PDF", height=40,
            fg_color="#00A9DC", hover_color="#0785AC",
            command=self.exportar_cotizacion_pdf
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            botones_exportacion, text="Exportar Excel", height=40,
            fg_color="#1D6F42", hover_color="#155230",
            command=self.exportar_cotizacion_excel
        ).pack(side="left", padx=6)

        self.agregar_item_cotizacion()

    def agregar_item_cotizacion(self):
        frame = self.frame_cotizacion_items
        fila = len(self.cotizacion_items) + 1
        cantidad = ctk.CTkEntry(frame, width=65, placeholder_text="1")
        descripcion = ctk.CTkEntry(frame, placeholder_text="Descripción del producto")
        valor_unitario = ctk.CTkEntry(frame, width=125, placeholder_text="0")
        valor_total = ctk.CTkLabel(frame, text="—", width=125)
        cantidad.grid(row=fila, column=0, sticky="ew", padx=3, pady=3)
        descripcion.grid(row=fila, column=1, sticky="ew", padx=3, pady=3)
        valor_unitario.grid(row=fila, column=2, sticky="ew", padx=3, pady=3)
        valor_total.grid(row=fila, column=3, sticky="ew", padx=3, pady=3)
        item = {
            "cantidad": cantidad,
            "descripcion": descripcion,
            "valor_unitario": valor_unitario,
            "valor_total": valor_total,
        }
        eliminar = ctk.CTkButton(
            frame, text="×", width=30, fg_color="gray35",
            command=lambda fila_item=item: self.eliminar_item_cotizacion(fila_item)
        )
        eliminar.grid(row=fila, column=4, padx=3, pady=3)
        item["eliminar"] = eliminar
        self.cotizacion_items.append(item)
        cantidad.bind("<KeyRelease>", self.actualizar_totales_cotizacion)
        valor_unitario.bind("<KeyRelease>", self.actualizar_totales_cotizacion)

    def eliminar_item_cotizacion(self, item):
        for widget in item.values():
            widget.destroy()
        self.cotizacion_items.remove(item)
        for fila, linea in enumerate(self.cotizacion_items, start=1):
            for columna, clave in enumerate(
                ("cantidad", "descripcion", "valor_unitario", "valor_total", "eliminar")
            ):
                linea[clave].grid_configure(row=fila, column=columna)
        self.actualizar_totales_cotizacion()

    def actualizar_totales_cotizacion(self, _evento=None):
        subtotal = 0
        for item in self.cotizacion_items:
            try:
                cantidad = cot_mod.parsear_cantidad(item["cantidad"].get())
                valor_unitario = cot_mod.parsear_valor(item["valor_unitario"].get())
            except ValueError:
                item["valor_total"].configure(text="—")
                continue
            total_linea = cantidad * valor_unitario
            subtotal += total_linea
            item["valor_total"].configure(text=cot_mod.formatear_pesos(total_linea))
        self.lbl_total_cotizacion.configure(text=f"TOTAL: {cot_mod.formatear_pesos(subtotal)}")

    def obtener_cotizacion_formulario(self):
        lineas = [{
            "cantidad": item["cantidad"].get(),
            "descripcion": item["descripcion"].get(),
            "valor_unitario": item["valor_unitario"].get(),
        } for item in self.cotizacion_items]
        return cot_mod.calcular_cotizacion(
            cliente=self.cot_cliente.get(),
            nit=self.cot_nit.get(),
            direccion=self.cot_direccion.get(),
            telefono=self.cot_telefono.get(),
            fecha=self.cot_fecha.get(),
            numero=self.cot_numero.get(),
            items=lineas,
            fecha_entrega=self.cot_fecha_entrega.get(),
            garantia=self.cot_garantia.get(),
        )

    def seleccionar_ruta_cotizacion(self, cotizacion, extension, tipo_archivo):
        numero_archivo = re.sub(r"[^\w-]+", "_", cotizacion["numero"]).strip("_") or "sin_numero"
        os.makedirs(self.carpeta_cotizaciones, exist_ok=True)
        return filedialog.asksaveasfilename(
            initialdir=os.path.abspath(self.carpeta_cotizaciones),
            initialfile=f"cotizacion_{numero_archivo}.{extension}",
            defaultextension=f".{extension}",
            filetypes=[(tipo_archivo, f"*.{extension}")],
        )

    def exportar_cotizacion_pdf(self):
        try:
            cotizacion = self.obtener_cotizacion_formulario()
        except ValueError as error:
            messagebox.showerror("Revisa los datos", str(error))
            return
        ruta = self.seleccionar_ruta_cotizacion(cotizacion, "pdf", "PDF")
        if not ruta:
            return
        try:
            cot_mod.exportar_pdf(ruta, cotizacion)
        except PermissionError:
            messagebox.showerror("Error", "No se pudo guardar. Cierra el PDF si está abierto e inténtalo de nuevo.")
            return
        except Exception as error:
            messagebox.showerror("Error al generar PDF", str(error))
            return
        messagebox.showinfo("Cotización exportada", f"PDF guardado en:\n{ruta}")

    def exportar_cotizacion_excel(self):
        try:
            cotizacion = self.obtener_cotizacion_formulario()
        except ValueError as error:
            messagebox.showerror("Revisa los datos", str(error))
            return
        ruta = self.seleccionar_ruta_cotizacion(cotizacion, "xlsx", "Excel")
        if not ruta:
            return
        try:
            cot_mod.exportar_excel(ruta, cotizacion)
        except PermissionError:
            messagebox.showerror("Error", "No se pudo guardar. Cierra el archivo Excel si está abierto e inténtalo de nuevo.")
            return
        except Exception as error:
            messagebox.showerror("Error al generar Excel", str(error))
            return
        messagebox.showinfo("Cotización exportada", f"Archivo Excel guardado en:\n{ruta}")

    # =========================================================================
    # PESTAÑA 3: LIQUIDACIÓN DE TRABAJADOR (COLOMBIA)
    # =========================================================================
    def construir_tab_liquidacion(self):
        self.liq_resultado = None
        cont = ctk.CTkScrollableFrame(self.tab_liquidacion)
        cont.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkLabel(cont, text="Liquidación de contrato de trabajo (Colombia)",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(5, 8))

        form = ctk.CTkFrame(cont)
        form.pack(fill="x", padx=10, pady=5)
        form.grid_columnconfigure((1, 3), weight=1)

        def fila(r, c, texto, widget):
            ctk.CTkLabel(form, text=texto, anchor="w").grid(row=r, column=c * 2, sticky="w", padx=(10, 4), pady=4)
            widget.grid(row=r, column=c * 2 + 1, sticky="ew", padx=(0, 10), pady=4)
            return widget

        self.liq_nombre = fila(0, 0, "Trabajador:", ctk.CTkEntry(form, placeholder_text="(opcional)"))
        self.liq_cedula = fila(0, 1, "Cédula (C.C.):", ctk.CTkEntry(form, placeholder_text="Ej: 1.111.111.111"))
        self.liq_cargo = fila(1, 0, "Cargo:", ctk.CTkEntry(form, placeholder_text="Ej: Auxiliar de planta"))
        self.liq_tipo = fila(1, 1, "Tipo de contrato:", ctk.CTkComboBox(form, values=liq_mod.TIPOS_CONTRATO, state="readonly"))
        self.liq_tipo.set("Indefinido")
        self.liq_ingreso = fila(2, 0, "Fecha ingreso:", ctk.CTkEntry(form, placeholder_text="AAAA-MM-DD"))
        self.liq_retiro = fila(2, 1, "Fecha retiro:", ctk.CTkEntry(form, placeholder_text="AAAA-MM-DD"))
        self.liq_salario = fila(3, 0, "Salario mensual ($):", ctk.CTkEntry(form, placeholder_text="1750905"))
        self.liq_promedio = fila(3, 1, "Salario promedio ($):", ctk.CTkEntry(form, placeholder_text="solo si es variable"))
        self.liq_motivo = fila(4, 0, "Motivo del retiro:", ctk.CTkComboBox(form, values=liq_mod.MOTIVOS, state="readonly"))
        self.liq_motivo.set("Renuncia")
        self.liq_fin = fila(4, 1, "Fin pactado:", ctk.CTkEntry(form, placeholder_text="fijo/obra: AAAA-MM-DD"))
        self.liq_vac = fila(5, 0, "Vacaciones disfrutadas (días hábiles):", ctk.CTkEntry(form))
        self.liq_vac.insert(0, "0")
        self.liq_pend = fila(5, 1, "Días de salario sin pagar:", ctk.CTkEntry(form))
        self.liq_pend.insert(0, "0")
        self.liq_extras = fila(6, 0, "Horas extras pendientes ($):", ctk.CTkEntry(form))
        self.liq_extras.insert(0, "0")
        self.liq_prestamos = fila(6, 1, "Préstamos / Anticipos ($):", ctk.CTkEntry(form))
        self.liq_prestamos.insert(0, "0")
        self.liq_aux = fila(7, 0, "Auxilio de transporte:", ctk.CTkComboBox(form, values=["Auto", "Sí", "No"], state="readonly"))
        self.liq_aux.set("Auto")
        self.liq_ces_desde = fila(7, 1, "Cesantías adeudadas desde:", ctk.CTkEntry(form, placeholder_text="opcional AAAA-MM-DD"))
        self.liq_smmlv = fila(8, 0, "SMMLV ($):", ctk.CTkEntry(form))
        self.liq_smmlv.insert(0, str(liq_mod.SMMLV_2026))
        self.liq_prima_desde = fila(8, 1, "Prima adeudada desde:", ctk.CTkEntry(form, placeholder_text="opcional AAAA-MM-DD"))
        self.liq_at = fila(9, 0, "Aux. transporte ($):", ctk.CTkEntry(form))
        self.liq_at.insert(0, str(liq_mod.AUXILIO_TRANSPORTE_2026))

        botones = ctk.CTkFrame(cont, fg_color="transparent")
        botones.pack(pady=8)
        ctk.CTkButton(botones, text="Calcular liquidación", command=self.calcular_liquidacion_ui).pack(side="left", padx=6)
        self.btn_liq_csv = ctk.CTkButton(botones, text="Exportar CSV", fg_color="gray30", state="disabled",
                                         command=self.exportar_liquidacion_csv)
        self.btn_liq_csv.pack(side="left", padx=6)
        self.btn_liq_xlsx = ctk.CTkButton(botones, text="Exportar Excel", fg_color="#1D6F42", hover_color="#155230",
                                          state="disabled", command=self.exportar_liquidacion_excel)
        self.btn_liq_xlsx.pack(side="left", padx=6)
        self.btn_liq_pdf = ctk.CTkButton(botones, text="Exportar PDF", fg_color="#B03A3A", hover_color="#8A2C2C",
                                         state="disabled", command=self.exportar_liquidacion_pdf)
        self.btn_liq_pdf.pack(side="left", padx=6)

        self.liq_texto = ctk.CTkTextbox(cont, height=230, font=ctk.CTkFont(family="Courier", size=12))
        self.liq_texto.pack(fill="x", padx=10, pady=(0, 10))

    def calcular_liquidacion_ui(self):
        def num(entry, nombre, defecto=None):
            t = entry.get().strip().replace(".", "").replace(",", "").replace("$", "")
            if not t:
                if defecto is not None:
                    return defecto
                raise ValueError(f"Falta: {nombre}")
            return float(t)

        def fecha_opcional(entry):
            t = entry.get().strip()
            return liq_mod.parsear_fecha(t) if t else None

        try:
            ingreso = liq_mod.parsear_fecha(self.liq_ingreso.get())
            retiro = liq_mod.parsear_fecha(self.liq_retiro.get())
            res = liq_mod.calcular_liquidacion(
                fecha_ingreso=ingreso,
                fecha_retiro=retiro,
                salario_mensual=num(self.liq_salario, "salario mensual"),
                tipo_contrato=self.liq_tipo.get(),
                motivo=self.liq_motivo.get(),
                fecha_fin_pactada=fecha_opcional(self.liq_fin),
                salario_promedio=num(self.liq_promedio, "", 0) or None,
                auxilio=self.liq_aux.get(),
                dias_vacaciones_disfrutados=num(self.liq_vac, "", 0),
                dias_salario_pendiente=int(num(self.liq_pend, "", 0)),
                cesantias_desde=fecha_opcional(self.liq_ces_desde),
                prima_desde=fecha_opcional(self.liq_prima_desde),
                smmlv=num(self.liq_smmlv, "SMMLV"),
                auxilio_transporte=num(self.liq_at, "auxilio de transporte"),
            )
        except ValueError as e:
            messagebox.showerror("Revisa los datos", str(e))
            return

        self.liq_resultado = res
        self.liq_datos = {
            "Trabajador": self.liq_nombre.get().strip() or "-",
            "Cedula": self.liq_cedula.get().strip(),
            "Cargo": self.liq_cargo.get().strip(),
            "Tipo de contrato": self.liq_tipo.get(),
            "Motivo": self.liq_motivo.get(),
            "Motivo del retiro": self.liq_motivo.get(),
            "Fecha de ingreso": ingreso.isoformat(),
            "Fecha de retiro": retiro.isoformat(),
            "Salario mensual": num(self.liq_salario, "salario mensual"),
            "Salario promedio": num(self.liq_promedio, "", 0) or None,
            "Dias vacaciones disfrutados": num(self.liq_vac, "", 0),
            "Horas extras": num(self.liq_extras, "", 0),
            "Prestamos": num(self.liq_prestamos, "", 0),
            "Empleador": "PROALUM",
        }
        pesos = liq_mod.formato_pesos
        lineas = []
        nombre = self.liq_nombre.get().strip()
        if nombre:
            lineas.append(f"Trabajador: {nombre}")
        lineas.append(f"Periodo: {ingreso} a {retiro}  ({res.dias_totales} días, año de 360)")
        lineas.append(f"Auxilio de transporte en la base: {'Sí' if res.aplica_auxilio else 'No'}")
        lineas.append("=" * 64)
        for c in res.conceptos:
            lineas.append(f"{c.nombre:<42}{pesos(c.valor):>20}")
            lineas.append(f"   {c.detalle}")
        lineas.append("=" * 64)
        lineas.append(f"{'TOTAL A PAGAR (bruto)':<42}{pesos(res.total):>20}")
        lineas.append("")
        for a in res.advertencias:
            lineas.append(f"• {a}")

        self.liq_texto.delete("1.0", "end")
        self.liq_texto.insert("1.0", "\n".join(lineas))
        self.btn_liq_csv.configure(state="normal")
        self.btn_liq_xlsx.configure(state="normal")
        self.btn_liq_pdf.configure(state="normal")

    def exportar_liquidacion_excel(self):
        if not self.liq_resultado:
            return
        sugerido = (self.liq_datos.get("Trabajador", "") or "liquidacion").replace(" ", "_")
        ruta = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")],
                                            initialfile=f"liquidacion_{sugerido}.xlsx")
        if not ruta:
            return
        try:
            liq_mod.exportar_excel(self.liq_resultado, ruta, self.liq_datos)
        except PermissionError:
            messagebox.showerror("Error", "No se pudo guardar. ¿Tienes el archivo abierto en Excel?")
            return
        messagebox.showinfo("Exportado", f"Guardado en:\n{ruta}")

    def exportar_liquidacion_csv(self):
        if not self.liq_resultado:
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile="liquidacion.csv")
        if not ruta:
            return
        with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Concepto", "Valor", "Detalle"])
            for c in self.liq_resultado.conceptos:
                w.writerow([c.nombre, c.valor, c.detalle])
            w.writerow(["TOTAL", self.liq_resultado.total, ""])
        messagebox.showinfo("Exportado", f"Guardado en:\n{ruta}")

    def exportar_liquidacion_pdf(self):
        if not self.liq_resultado:
            return
        sugerido = (self.liq_datos.get("Trabajador", "") or "liquidacion").replace(" ", "_")
        ruta = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
                                            initialfile=f"liquidacion_{sugerido}.pdf")
        if not ruta:
            return
        try:
            liq_mod.exportar_pdf(self.liq_resultado, ruta, self.liq_datos)
        except PermissionError:
            messagebox.showerror("Error", "No se pudo guardar. ¿Tienes el archivo abierto en otro programa?")
            return
        except Exception as e:
            messagebox.showerror("Error al generar PDF", str(e))
            return
        messagebox.showinfo("Exportado", f"Guardado en:\n{ruta}")


if __name__ == "__main__":
    app = AppProspeccion()
    app.mainloop()
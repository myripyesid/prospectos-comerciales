"""
Bot de WhatsApp Web (Playwright + Chromium) con dos modos:

  - "auto":   el bot abre el chat, escribe el mensaje y presiona Enter solo.
  - "manual": el bot abre el chat con el mensaje prellenado y espera a que TÚ
              presiones Enter en WhatsApp; cuando detecta que se envió, sigue.

El modo se puede cambiar en caliente (incluso mientras espera tu Enter).
Toda la lógica de Playwright corre en un único hilo (requisito de la API sync).
"""
import csv
import os
import random
import re
import threading
import time
import urllib.parse
from datetime import datetime

from playwright.sync_api import sync_playwright

ESTADOS_FINALES = {"enviado", "no_whatsapp"}  # no se reintentan nunca

SEL_PANEL = "#pane-side"
SEL_COMPOSER = [
    'footer div[contenteditable="true"][role="textbox"]',
    'footer div[contenteditable="true"][data-tab="10"]',
    'footer div[contenteditable="true"]',
]
SEL_DIALOGO = 'div[role="dialog"], div[data-animate-modal-popup="true"]'
RE_INVALIDO = re.compile(
    r"no es v[aá]lid|inv[aá]lid|not on whatsapp|invalid|no est[aá] en whatsapp|"
    r"no tiene whatsapp|isn't on whatsapp",
    re.I,
)

CONFIG_DEFECTO = {
    "max_por_dia": 20,
    "hora_inicio": 8,        # solo envía entre hora_inicio y hora_fin (hora local)
    "hora_fin": 18,
    "pausa_min": 45,         # segundos entre mensajes
    "pausa_max": 120,
    "lote_tamano": 5,        # cada N enviados, pausa larga
    "lote_pausa_min": 240,
    "lote_pausa_max": 480,
    "timeout_manual": 600,   # segundos esperando tu Enter antes de pausar
    "errores_seguidos_max": 3,
}


class BotWhatsApp:
    def __init__(self, contactos, generar_mensaje, ruta_log, perfil_dir,
                 modo="manual", config=None,
                 on_log=print, on_progreso=lambda i, n: None, on_fin=lambda: None):
        """
        contactos:        lista de (nombre, numero_con_57)
        generar_mensaje:  callable(nombre) -> str
        ruta_log:         CSV persistente de resultados (evita reenviar)
        perfil_dir:       carpeta del perfil de Chromium (guarda la sesión/QR)
        """
        self.contactos = contactos
        self.generar_mensaje = generar_mensaje
        self.ruta_log = ruta_log
        self.perfil_dir = perfil_dir
        self.modo = modo
        self.cfg = {**CONFIG_DEFECTO, **(config or {})}
        self.on_log = on_log
        self.on_progreso = on_progreso
        self.on_fin = on_fin

        self._stop = threading.Event()
        self._pausa = threading.Event()
        self._hilo = None
        self.page = None

    # ------------------------------------------------------------------ control
    def iniciar(self):
        self._stop.clear()
        self._pausa.clear()
        self._hilo = threading.Thread(target=self._run, daemon=True)
        self._hilo.start()

    def detener(self):
        self._stop.set()

    def pausar(self, valor=True):
        (self._pausa.set if valor else self._pausa.clear)()

    @property
    def activo(self):
        return self._hilo is not None and self._hilo.is_alive()

    # ------------------------------------------------------------------ utilidades
    def _esperar(self, segundos):
        """Sleep interrumpible por Stop. Respeta la pausa."""
        fin = time.time() + segundos
        while time.time() < fin:
            if self._stop.is_set():
                return False
            time.sleep(0.4)
        return True

    def _esperar_si_pausado(self):
        avisado = False
        while self._pausa.is_set() and not self._stop.is_set():
            if not avisado:
                self.on_log("⏸ En pausa...")
                avisado = True
            time.sleep(0.4)
        return not self._stop.is_set()

    def _leer_log(self):
        hechos, enviados_hoy = set(), 0
        hoy = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(self.ruta_log):
            with open(self.ruta_log, newline="", encoding="utf-8-sig") as f:
                for fila in csv.DictReader(f):
                    if fila["estado"] in ESTADOS_FINALES:
                        hechos.add(fila["numero"])
                    if fila["estado"] == "enviado" and fila["fecha_hora"].startswith(hoy):
                        enviados_hoy += 1
        return hechos, enviados_hoy

    def _registrar(self, nombre, numero, estado, modo):
        nuevo = not os.path.exists(self.ruta_log)
        with open(self.ruta_log, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if nuevo:
                w.writerow(["fecha_hora", "numero", "nombre", "estado", "modo"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), numero, nombre, estado, modo])

    def _en_ventana_horaria(self):
        return self.cfg["hora_inicio"] <= datetime.now().hour < self.cfg["hora_fin"]

    # ------------------------------------------------------------------ DOM
    def _composer(self):
        for sel in SEL_COMPOSER:
            loc = self.page.locator(sel).first
            if loc.count() and loc.is_visible():
                return loc
        return None

    def _texto_composer(self):
        c = self._composer()
        return (c.inner_text().strip() if c else "")

    def _esperar_login(self):
        self.on_log("Abriendo WhatsApp Web... si aparece el QR, escanéalo (tienes 3 min).")
        self.page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded")
        fin = time.time() + 180
        while time.time() < fin and not self._stop.is_set():
            if self.page.locator(SEL_PANEL).count():
                self.on_log("Sesión de WhatsApp Web lista.")
                return True
            time.sleep(1)
        return False

    def _abrir_chat(self, numero, mensaje):
        """Devuelve 'listo' | 'no_whatsapp' | 'sin_sesion' | 'timeout'."""
        url = f"https://web.whatsapp.com/send?phone={numero}&text={urllib.parse.quote(mensaje)}"
        self.page.goto(url, wait_until="domcontentloaded")
        fin = time.time() + 60
        while time.time() < fin and not self._stop.is_set():
            dlg = self.page.locator(SEL_DIALOGO).first
            if dlg.count():
                try:
                    if RE_INVALIDO.search(dlg.inner_text(timeout=1000)):
                        return "no_whatsapp"
                except Exception:
                    pass
            if self._composer():
                return "listo"
            if self.page.locator("canvas[aria-label], div[data-ref]").count() \
                    and not self.page.locator(SEL_PANEL).count() and time.time() > fin - 40:
                return "sin_sesion"
            time.sleep(0.8)
        return "timeout"

    def _asegurar_texto(self, mensaje):
        """Si el prellenado por URL falló, escribe el mensaje a mano."""
        for _ in range(10):
            if self._texto_composer():
                return True
            time.sleep(0.5)
        c = self._composer()
        if not c:
            return False
        c.click()
        self.page.keyboard.insert_text(mensaje)
        return bool(self._texto_composer())

    def _enviar_auto(self):
        time.sleep(random.uniform(2, 5))          # "lectura" antes de enviar
        self.page.keyboard.press("Enter")
        return self._esperar_composer_vacio(15)

    def _esperar_composer_vacio(self, timeout):
        fin = time.time() + timeout
        while time.time() < fin and not self._stop.is_set():
            if not self._texto_composer():
                return True
            time.sleep(0.5)
        return False

    def _enviar_manual(self):
        """Espera tu Enter. Si cambias a auto mientras espera, envía el bot."""
        self.on_log("👉 Presiona ENTER en WhatsApp para enviar (o cambia a Automático).")
        fin = time.time() + self.cfg["timeout_manual"]
        while time.time() < fin and not self._stop.is_set():
            if not self._texto_composer():
                return "enviado"
            if self.modo == "auto":
                self.on_log("Cambiado a automático: el bot envía este mensaje.")
                return "enviado" if self._enviar_auto() else "error"
            time.sleep(0.5)
        return "timeout_manual"

    # ------------------------------------------------------------------ bucle
    def _run(self):
        try:
            self._bucle()
        except Exception as e:  # el navegador cerrado a mano cae aquí
            self.on_log(f"⛔ Error: {e}")
        finally:
            self.on_log("Bot detenido.")
            self.on_fin()

    def _bucle(self):
        hechos, enviados_hoy = self._leer_log()
        pendientes = [(n, t) for n, t in self.contactos if t not in hechos]
        total = len(pendientes)
        self.on_log(f"Pendientes: {total} (ya procesados antes: {len(self.contactos) - total}). "
                    f"Enviados hoy: {enviados_hoy}/{self.cfg['max_por_dia']}.")
        if not pendientes:
            return

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                self.perfil_dir, headless=False, viewport=None,
                args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
            )
            try:
                self.page = ctx.pages[0] if ctx.pages else ctx.new_page()
                self.page.on("dialog", lambda d: d.accept())  # "¿salir del sitio?"
                if not self._esperar_login():
                    self.on_log("No se inició sesión a tiempo.")
                    return

                errores_seguidos, en_lote = 0, 0
                for i, (nombre, numero) in enumerate(pendientes, 1):
                    if not self._esperar_si_pausado():
                        break

                    # Ventana horaria: espera sin consumir cupo
                    while not self._en_ventana_horaria() and not self._stop.is_set():
                        self.on_log(f"Fuera de horario ({self.cfg['hora_inicio']}h-{self.cfg['hora_fin']}h). Esperando...")
                        if not self._esperar(300):
                            break
                    if self._stop.is_set():
                        break

                    if enviados_hoy >= self.cfg["max_por_dia"]:
                        self.on_log(f"Límite diario alcanzado ({enviados_hoy}). Continúa mañana.")
                        break

                    self.on_progreso(i, total)
                    self.on_log(f"[{i}/{total}] {nombre} (+{numero})")
                    mensaje = self.generar_mensaje(nombre)

                    estado = self._abrir_chat(numero, mensaje)
                    if estado == "listo":
                        if not self._asegurar_texto(mensaje):
                            estado = "error"
                        elif self.modo == "auto":
                            estado = "enviado" if self._enviar_auto() else "error"
                        else:
                            estado = self._enviar_manual()
                    elif estado == "sin_sesion":
                        self.on_log("⛔ Se perdió la sesión de WhatsApp Web. Deteniendo.")
                        break

                    if self._stop.is_set():
                        break

                    modo_usado = self.modo
                    self._registrar(nombre, numero, estado, modo_usado)
                    self.on_log(f"   → {estado}")

                    if estado == "enviado":
                        enviados_hoy += 1
                        en_lote += 1
                        errores_seguidos = 0
                        pausa = random.uniform(self.cfg["pausa_min"], self.cfg["pausa_max"])
                        if en_lote >= self.cfg["lote_tamano"]:
                            en_lote = 0
                            pausa = random.uniform(self.cfg["lote_pausa_min"], self.cfg["lote_pausa_max"])
                            self.on_log(f"Pausa larga de {int(pausa // 60)} min {int(pausa % 60)} s...")
                        else:
                            self.on_log(f"Siguiente en {int(pausa)} s...")
                        if not self._esperar(pausa):
                            break
                    elif estado == "no_whatsapp":
                        errores_seguidos = 0
                        if not self._esperar(random.uniform(5, 10)):
                            break
                    elif estado == "timeout_manual":
                        self.on_log("Sin respuesta tuya a tiempo: bot en pausa. Reanuda cuando quieras.")
                        self.pausar(True)
                    else:  # error / timeout
                        errores_seguidos += 1
                        if errores_seguidos >= self.cfg["errores_seguidos_max"]:
                            self.on_log("⛔ Varios errores seguidos: me detengo por seguridad.")
                            break
                        if not self._esperar(random.uniform(20, 40)):
                            break
                else:
                    self.on_log("✅ Lista completada.")
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass

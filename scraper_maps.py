import time
import random  
import pandas as pd
import os  
from playwright.sync_api import sync_playwright

def scrape_google_maps(busqueda):
    resultados = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print(f"Buscando: {busqueda}...")
        page.goto(f"https://www.google.com/maps/search/{busqueda.replace(' ', '+')}")
        
        page.wait_for_selector('div[role="feed"]', timeout=15000)
        panel_resultados = page.locator('div[role="feed"]')

        print("Cargando todos los resultados disponibles...")
        while True:
            panel_resultados.evaluate("el => el.scrollBy(0, 3000)")
            
            # <--- 2. Pausa aleatoria mientras hace scroll (reemplaza el time.sleep(2))
            time.sleep(random.uniform(2.0, 4.0)) 
            
            if page.locator("text=Has llegado al final de la lista").is_visible() or \
               page.locator("text=You've reached the end of the list").is_visible():
                break

        enlaces = page.locator('a[href*="/maps/place/"]').all()
        urls_unicas = list(dict.fromkeys([e.get_attribute("href") for e in enlaces]))
        print(f"Se encontraron {len(urls_unicas)} negocios. Extrayendo detalles...")

        for idx, url in enumerate(urls_unicas, 1):
            try:
                page.goto(url)
                page.wait_for_selector('h1', timeout=10000)
                
                nombre = page.locator('h1').inner_text()
                
                direccion_el = page.locator('button[data-item-id="address"]')
                direccion = direccion_el.inner_text() if direccion_el.count() > 0 else "No disponible"
                
                telefono_el = page.locator('button[data-item-id*="phone:tel:"]')
                telefono = telefono_el.inner_text() if telefono_el.count() > 0 else "No disponible"

                direccion = direccion.replace('\n', ' ').strip()
                telefono = telefono.replace('\n', ' ').strip()

                resultados.append({
                    "Nombre": nombre,
                    "Dirección": direccion,
                    "Teléfono": telefono
                })
                print(f"[{idx}/{len(urls_unicas)}] {nombre} | {telefono}")

                # <--- 3. Pausa aleatoria antes de abrir el siguiente negocio
                time.sleep(random.uniform(2.5, 5.0))
                
            except Exception as e:
                print(f"Error extrayendo negocio {idx}: {e}")

        browser.close()

    if resultados:
        df = pd.DataFrame(resultados)
        nombre_archivo = busqueda.replace(" ", "_").lower()

        # Definir nombres de carpetas y crearlas automáticamente si no existen
        carpeta_excel = "resultados_excel"
        carpeta_csv = "resultados_csv"
        os.makedirs(carpeta_excel, exist_ok=True)
        os.makedirs(carpeta_csv, exist_ok=True)

        # Filtrar los datos en dos tablas distintas
        df_con_telefono = df[df["Teléfono"] != "No disponible"]
        df_sin_telefono = df[df["Teléfono"] == "No disponible"]

        # 1. Guardar Excel en su carpeta (2 pestañas)
        ruta_excel = os.path.join(carpeta_excel, f"{nombre_archivo}.xlsx")
        with pd.ExcelWriter(ruta_excel, engine="openpyxl") as writer:
            df_con_telefono.to_excel(writer, sheet_name="Con Teléfono", index=False)
            df_sin_telefono.to_excel(writer, sheet_name="Sin Teléfono", index=False)

        # 2. Guardar CSVs en su carpeta
        ruta_csv_con = os.path.join(carpeta_csv, f"{nombre_archivo}_con_telefono.csv")
        ruta_csv_sin = os.path.join(carpeta_csv, f"{nombre_archivo}_sin_telefono.csv")
        
        df_con_telefono.to_csv(ruta_csv_con, index=False, encoding="utf-8-sig")
        df_sin_telefono.to_csv(ruta_csv_sin, index=False, encoding="utf-8-sig")

        print(f"\n¡Listo! Total encontrados: {len(df)}")
        print(f"- Con teléfono: {len(df_con_telefono)}")
        print(f"- Sin teléfono: {len(df_sin_telefono)}")
        print(f"Excel guardado en: {ruta_excel}")
        print(f"CSVs guardados en: {carpeta_csv}/")
    else:
        print("No se extrajeron datos.")

if __name__ == "__main__":
    termino = input("Ingresa tu búsqueda (Ej. Panadería en Itagui): ")
    scrape_google_maps(termino)
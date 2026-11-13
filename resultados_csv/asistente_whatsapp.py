import os
import re
import time
import random
import urllib.parse
import webbrowser
import pandas as pd

def limpiar_celular_colombia(telefono):
    # Quita espacios, guiones, paréntesis y el +57 si ya lo tiene
    digitos = re.sub(r'\D', '', str(telefono))
    if digitos.startswith('57') and len(digitos) == 12:
        digitos = digitos[2:]
    
    # En Colombia los celulares tienen 10 dígitos y empiezan por 3
    if len(digitos) == 10 and digitos.startswith('3'):
        return f"57{digitos}"
    return None

def generar_mensaje_spintax(nombre_negocio, municipio):
    saludos = [
        "Hola, ¿cómo están?",
        "Hola, buen día.",
        "Buenas tardes, ¿cómo les va?",
        "Hola, un saludo."
    ]
    intro = [
        f"Les escribo a *{nombre_negocio}*",
        f"Me comunico con *{nombre_negocio}*",
        f"Vi a *{nombre_negocio}* en Maps y les escribo"
    ]
    cuerpo = [
        f"porque estamos apoyando varios negocios en {municipio} con renovación de exhibición y mobiliario comercial.",
        f"ya que trabajamos con locales fabricando vitrinas y exhibidores a medida.",
        f"porque estamos asesorando comercios en {municipio} en temas de exhibición y vitrinas."
    ]
    cierre = [
        "¿Por este medio me pueden comunicar con el encargado o administrador? Gracias.",
        "¿Por este medio puedo hablar con la persona encargada? Muchas gracias.",
        "¿Me podrían indicar si este es el contacto del administrador? Quedo atento, gracias."
    ]
    
    return f"{random.choice(saludos)} {random.choice(intro)} {random.choice(cuerpo)} {random.choice(cierre)}"

def iniciar_campana(ruta_csv, municipio, limite_diario=20):
    df = pd.read_csv(ruta_csv)
    
    # 1. Filtrar solo celulares válidos de Colombia
    df['Celular_Limpio'] = df['Teléfono'].apply(limpiar_celular_colombia)
    celulares_validos = df.dropna(subset=['Celular_Limpio']).copy()
    
    # Guardar los fijos aparte para llamarlos después
    fijos = df[df['Celular_Limpio'].isna()]
    fijos.to_csv("telefonos_fijos_para_llamar.csv", index=False, encoding="utf-8-sig")
    
    print(f"Total en archivo: {len(df)}")
    print(f"Celulares listos para WhatsApp: {len(celulares_validos)}")
    print(f"Teléfonos fijos guardados en 'telefonos_fijos_para_llamar.csv': {len(fijos)}\n")

    # 2. Procesar hasta el límite diario recomendado
    lote = celulares_validos.head(limite_diario)
    
    for idx, fila in lote.iterrows():
        nombre = fila['Nombre']
        numero = fila['Celular_Limpio']
        mensaje = generar_mensaje_spintax(nombre, municipio)
        
        # Crear enlace oficial de WhatsApp con texto prellenado
        texto_codificado = urllib.parse.quote(mensaje)
        url_wa = f"https://web.whatsapp.com/send?phone={numero}&text={texto_codificado}"
        
        print(f"Abriendo chat con: {nombre} (+{numero})")
        print(f"Mensaje generado: {mensaje}\n")
        
        webbrowser.open(url_wa)
        
        # Espera confirmación manual + pausa aleatoria anti-spam
        input(">>> Presiona ENTER en WhatsApp para enviar, y luego ENTER aquí para preparar el siguiente...")
        espera = random.uniform(15, 35)
        print(f"Esperando {int(espera)} segundos antes del siguiente contacto...\n")
        time.sleep(espera)

if __name__ == "__main__":
    # Detectar si estás dentro de 'resultados_csv' o en la carpeta principal
    carpeta = "." if os.path.basename(os.getcwd()) == "resultados_csv" else "resultados_csv"
    
    if not os.path.exists(carpeta):
        print(f"No se encontró la carpeta '{carpeta}'.")
        exit()

    # Listar solo los archivos que terminan en _con_telefono.csv
    archivos = [f for f in os.listdir(carpeta) if f.endswith("_con_telefono.csv")]

    if not archivos:
        print("No hay archivos '_con_telefono.csv' disponibles.")
        exit()

    print("\nArchivos disponibles:")
    for i, nombre_archivo in enumerate(archivos, 1):
        print(f"{i}. {nombre_archivo}")

    opcion = int(input("\nElige el número del archivo que quieres usar: ")) - 1
    ruta_elegida = os.path.join(carpeta, archivos[opcion])
    
    ciudad = input("Nombre del municipio/ciudad para el mensaje (Ej. Barbosa): ")
    iniciar_campana(ruta_elegida, ciudad, limite_diario=20)
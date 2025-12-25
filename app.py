from flask import Flask, request, send_file, render_template
from rembg import remove, new_session
from PIL import Image
import cv2
import numpy as np
import io
import hashlib
import time
import requests
from functools import lru_cache
from numba import jit
import logging
from dotenv import load_dotenv
import os
from flask_cors import CORS

# ================== LOGGING ==================
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)

# ================== APP ==================
app = Flask(__name__)
CORS(app)
# ================== CONFIGURACIÓN ==================
load_dotenv()
ARTGURU_API_KEY = os.getenv("APIKEY")
rembg_session = new_session("isnet-general-use")
log.info("Aplicación iniciada")
log.info("Sesión rembg cargada (isnet-general-use)")

# ================== DITHERING ==================
@jit(nopython=True, fastmath=True)
def jarvis_dither_fast(img_gray, threshold):
    h, w = img_gray.shape
    img = img_gray.astype(np.float32)

    for y in range(h - 2):
        for x in range(2, w - 2):
            old_pix = img[y, x]
            new_pix = 255.0 if old_pix > threshold else 0.0
            img[y, x] = new_pix
            err = old_pix - new_pix

            img[y, x+1]   += err * (7/48);  img[y, x+2]   += err * (5/48)
            img[y+1, x-2] += err * (3/48); img[y+1, x-1] += err * (5/48); img[y+1, x] += err * (7/48)
            img[y+1, x+1] += err * (5/48); img[y+1, x+2] += err * (3/48)
            img[y+2, x-2] += err * (1/48); img[y+2, x-1] += err * (3/48); img[y+2, x] += err * (5/48)
            img[y+2, x+1] += err * (3/48); img[y+2, x+2] += err * (1/48)
    return img


# ================== ARTGURU AI ==================
def call_artguru_api(img_bgr):
    log.info("Iniciando flujo de mejora (Estructura JSON Final)")
    headers = {'x-api-key': ARTGURU_API_KEY}

    try:
        # 1. UPLOAD
        _, buffer = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        up_res = requests.post(
            "https://api.artguru.ai/api/v1/image/upload",
            headers=headers,
            files={'image': ('image.jpg', buffer.tobytes(), 'image/jpeg')},
            timeout=30
        )
        raw_url = up_res.json().get("data", {}).get("imageUrl")
        if not raw_url: return img_bgr

        # 2. GENERATE
        gen_res = requests.post(
            "https://api.artguru.ai/api/v1/enhance/generate",
            json={"image": raw_url},
            headers=headers,
            timeout=30
        )
        task_id = gen_res.json().get("data", {}).get("taskId")
        if not task_id: return img_bgr

        # 3. POLLING (Consultando exactamente como tu ejemplo)
        log.info(f"Tarea {task_id} en curso...")
        for i in range(20):
            time.sleep(2)
            
            url_consulta = f"https://api.artguru.ai/api/v1/tasks/ENHANCE/{task_id}"
            check_res = requests.get(url_consulta, headers=headers, timeout=10)
            
            if check_res.status_code == 200:
                full_json = check_res.json()
                data_obj = full_json.get("data", {})
                status = data_obj.get("status")
                
                log.debug(f"Intento {i+1}: Estado = {status}")

                if status == "SUCCESS":
                    # SEGÚN TU EJEMPLO: El link está en 'generateImage'
                    final_url = data_obj.get("generateUrl")
                    
                    if not final_url:
                        log.error(f"No se encontró 'generateUrl' en el JSON: {full_json}")
                        return img_bgr

                    log.info(f"¡Imagen lista! Descargando de: {final_url}")
                    img_res = requests.get(final_url, timeout=30)
                    nparr = np.frombuffer(img_res.content, np.uint8)
                    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                
                if status == "FAIL":
                    log.error("La IA de Artguru falló.")
                    break
            else:
                log.warning(f"Error {check_res.status_code} en consulta.")

        return img_bgr

    except Exception as e:
        log.error(f"Error crítico: {e}")
        return img_bgr
    
# ================== PIPELINE PESADO (CACHEADO) ==================
def add_padding_pil(img_pil, pad_ratio=0.08):
    w, h = img_pil.size
    pad_w = int(w * pad_ratio)
    pad_h = int(h * pad_ratio)

    padded = Image.new("RGB", (w + pad_w * 2, h + pad_h * 2), (255, 255, 255))
    padded.paste(img_pil, (pad_w, pad_h))

    return padded, pad_w, pad_h


@lru_cache(maxsize=15)
def procesar_pipeline_pesado(img_hash, img_bytes):
    log.info(f"Pipeline pesado (cache MISS): {img_hash}")
    start = time.time()

    nparr = np.frombuffer(img_bytes, np.uint8)
    img_original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_original is None:
        return None

    # 1. MEJORA CON ARTGURU
    img_mejorada = call_artguru_api(img_original)
    
    # --- OPTIMIZACIÓN CRUCIAL: REESCALADO ---
    # Artguru devuelve 4096px, lo cual es demasiado para procesar en cada slider.
    # Reducimos a un tamaño razonable para web (ej. 1200px)
    max_dim = 1200
    h, w = img_mejorada.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_mejorada = cv2.resize(img_mejorada, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        log.debug(f"Imagen reescalada para fluidez: {img_mejorada.shape}")

    # 2. PREPARAR PARA REMBG
    img_rgb = cv2.cvtColor(img_mejorada, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)

    # Padding preventivo
    w, h = img_pil.size
    pad_ratio = 0.10 # Reducido un poco para ganar velocidad
    pad_w, pad_h = int(w * pad_ratio), int(h * pad_ratio)

    img_padded = Image.new("RGB", (w + pad_w * 2, h + pad_h * 2), (255, 255, 255))
    img_padded.paste(img_pil, (pad_w, pad_h))

    # 3. QUITAR FONDO
    img_no_bg = remove(img_padded, session=rembg_session)

    # 4. PROCESO DE ALPHA Y RECORTADO
    result_rgba = np.array(img_no_bg, dtype=np.uint8)
    b, g, r, a = cv2.split(result_rgba)
    a = cv2.GaussianBlur(a, (5, 5), 0)
    result_rgba = cv2.merge([b, g, r, a])

    # Quitar padding
    h2, w2 = result_rgba.shape[:2]
    result_rgba = result_rgba[pad_h : h2 - pad_h, pad_w : w2 - pad_w]

    result = cv2.cvtColor(result_rgba, cv2.COLOR_RGBA2BGRA)
    log.info(f"Pipeline pesado finalizado en {time.time() - start:.2f}s")
    return result

# ================== PROCESAMIENTO ==================
def process_logic():
    log.info("Nueva petición de procesamiento")

    if "image" not in request.files:
        log.warning("No se recibió imagen")
        return "No image", 400

    file = request.files["image"]
    file.seek(0) # <--- Asegura que siempre leamos desde el principio del archivo
    img_bytes = file.read()
    if not img_bytes:
        log.warning("Imagen vacía")
        return "Empty", 400

    img_hash = hashlib.md5(img_bytes).hexdigest()
    log.debug(f"Hash imagen: {img_hash}")

    # Parámetros
    brightness = int(request.form.get("brightness", 0))
    contrast = float(request.form.get("contrast", 1.0))
    threshold = int(request.form.get("threshold", 128))
    pixel_size = int(request.form.get("pixel_size", 2))
    dither = request.form.get("dither") == "true"
    invert = request.form.get("invert") == "true"

    log.debug(f"Params → brightness={brightness}, contrast={contrast}, threshold={threshold}, pixel={pixel_size}, dither={dither}, invert={invert}")

    img_rgba = procesar_pipeline_pesado(img_hash, img_bytes)
    img_work = img_rgba.copy()

    b, g, r, a = cv2.split(img_work)
    img_bgr = cv2.merge([b, g, r])

    # Brillo / Contraste
    if contrast != 1.0 or brightness != 0:
        log.debug("Aplicando brillo/contraste")
        img_bgr = cv2.convertScaleAbs(img_bgr, alpha=contrast, beta=brightness)

    # Dithering CNC
    if dither:
        log.info("Aplicando dithering Jarvis")
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape
        log.debug(f"Gray size: {w}x{h}")

        new_w = max(1, w // pixel_size)
        new_h = max(1, h // pixel_size)
        log.debug(f"Reducido a: {new_w}x{new_h}")

        gray_small = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
        dithered = jarvis_dither_fast(gray_small, threshold)
        gray_final = cv2.resize(dithered, (w, h), interpolation=cv2.INTER_NEAREST)
        img_bgr = cv2.cvtColor(gray_final.astype(np.uint8), cv2.COLOR_GRAY2BGR)

    # Invertir
    if invert:
        log.debug("Invirtiendo imagen")
        img_bgr = cv2.bitwise_not(img_bgr)

    resultado = cv2.merge([img_bgr[:,:,0], img_bgr[:,:,1], img_bgr[:,:,2], a])

    _, buffer = cv2.imencode(".png", resultado)
    log.info("Imagen procesada correctamente")

    return send_file(io.BytesIO(buffer), mimetype="image/png")

# ================== RUTAS ==================
@app.route("/")
def index():
    log.debug("Ruta /")
    return render_template("index.html")

@app.route("/preview", methods=["POST"])
def preview_route():
    try:
        return process_logic()
    except Exception as e:
        log.error(f"Error en /preview: {str(e)}")
        return {"error": str(e)}, 500
    
@app.route("/export", methods=["POST"])
def export_route():
    log.debug("Ruta /export")
    return process_logic()

# ================== MAIN ==================
if __name__ == "__main__":
    log.info("Servidor Flask iniciado en http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
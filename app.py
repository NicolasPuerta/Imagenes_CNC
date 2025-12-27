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
# Sesión persistente para mayor velocidad
rembg_session = new_session("isnet-general-use")
log.info("Aplicación iniciada")
log.info(f"Sesión rembg cargada. API Key Artguru: {'Detectada' if ARTGURU_API_KEY else 'No detectada'}")

# ================== DITHERING JARVIS-JUDICE-NINKE (OPTIMIZADO) ==================
@jit(nopython=True, fastmath=True)
def jarvis_dither_fast(img_gray, threshold_val):
    h, w = img_gray.shape
    img = img_gray.astype(np.float32)

    for y in range(h - 2):
        for x in range(2, w - 2):
            old_pix = img[y, x]
            # Binarización basada en el umbral
            new_pix = 255.0 if old_pix > threshold_val else 0.0
            img[y, x] = new_pix
            err = old_pix - new_pix

            # Difusión de error de Jarvis (Matriz de 12 vecinos)
            img[y, x+1]   += err * (7/48);  img[y, x+2]   += err * (5/48)
            img[y+1, x-2] += err * (3/48); img[y+1, x-1] += err * (5/48); img[y+1, x] += err * (7/48)
            img[y+1, x+1] += err * (5/48); img[y+1, x+2] += err * (3/48)
            img[y+2, x-2] += err * (1/48); img[y+2, x-1] += err * (3/48); img[y+2, x] += err * (5/48)
            img[y+2, x+1] += err * (3/48); img[y+2, x+2] += err * (1/48)
    return img

# ================== ARTGURU AI ==================
def call_artguru_api(img_bgr):
    log.info("Iniciando flujo de mejora Artguru (v1 API)")
    if not ARTGURU_API_KEY:
        log.warning("Saltando Artguru: API KEY no configurada")
        return img_bgr

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

        # 3. POLLING
        for i in range(20):
            time.sleep(2)
            check_res = requests.get(f"https://api.artguru.ai/api/v1/tasks/ENHANCE/{task_id}", headers=headers)
            data_obj = check_res.json().get("data", {})
            status = data_obj.get("status")
            log.debug(f"Polling Artguru - Intento {i+1}: {status}")

            if status == "SUCCESS":
                final_url = data_obj.get("generateUrl")
                img_res = requests.get(final_url, timeout=30)
                return cv2.imdecode(np.frombuffer(img_res.content, np.uint8), cv2.IMREAD_COLOR)
            if status == "FAIL": break
        return img_bgr
    except Exception as e:
        log.error(f"Error en Artguru: {e}")
        return img_bgr

# ================== PIPELINE PESADO CON PADDING Y AUTO-CROP ==================
@lru_cache(maxsize=15)
def procesar_pipeline_pesado(img_hash, img_bytes):
    log.info(f"Pipeline pesado (Cache MISS): {img_hash}")
    start_time = time.time()

    nparr = np.frombuffer(img_bytes, np.uint8)
    img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # 1. Mejora IA
    img_enhanced = call_artguru_api(img_cv)
    
    # 2. Reescalado de alta calidad (2000px para granulado fino)
    max_dim = 2000
    h, w = img_enhanced.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img_enhanced = cv2.resize(img_enhanced, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        log.debug(f"Imagen reescalada a {img_enhanced.shape[1]}x{img_enhanced.shape[0]}")

    # 3. Padding Preventivo (Evita cortes malos en los bordes)
    img_rgb = cv2.cvtColor(img_enhanced, cv2.COLOR_BGR2RGB)
    img_pil = Image.fromarray(img_rgb)
    pad_v = int(max(img_pil.size) * 0.1) # 10% de margen
    img_padded = Image.new("RGB", (img_pil.width + pad_v*2, img_pil.height + pad_v*2), (255, 255, 255))
    img_padded.paste(img_pil, (pad_v, pad_v))

    # 4. Quitar fondo
    log.info("Eliminando fondo con Rembg...")
    img_no_bg = remove(img_padded, session=rembg_session)
    result_rgba = np.array(img_no_bg, dtype=np.uint8)

    # 5. Auto-Crop (Recortar transparencia sobrante)
    alpha = result_rgba[:, :, 3]
    coords = cv2.findNonZero(alpha)
    if coords is not None:
        x, y, w_c, h_c = cv2.boundingRect(coords)
        m = 5 # margen extra
        x_f, y_f = max(0, x-m), max(0, y-m)
        w_f, h_f = min(result_rgba.shape[1]-x_f, w_c+m*2), min(result_rgba.shape[0]-y_f, h_c+m*2)
        result_rgba = result_rgba[y_f:y_f+h_f, x_f:x_f+w_f]
        log.debug(f"Auto-crop realizado: {w_f}x{h_f}")

    # 6. Suavizar máscara de bordes
    b, g, r, a = cv2.split(result_rgba)
    a = cv2.GaussianBlur(a, (3, 3), 0)
    final_bgra = cv2.merge([b, g, r, a])

    log.info(f"Pipeline pesado terminado en {time.time() - start_time:.2f}s")
    return final_bgra

# ================== PROCESAMIENTO DINÁMICO ==================
def process_logic():
    if "image" not in request.files:
        return "No image", 400

    file = request.files["image"]
    img_bytes = file.read()
    img_hash = hashlib.md5(img_bytes).hexdigest()

    brightness = int(request.form.get("brightness", 0))
    contrast = float(request.form.get("contrast", 1.0))
    threshold = int(request.form.get("threshold", 128))
    pixel_size = int(request.form.get("pixel_size", 1))
    dither = request.form.get("dither") == "true"
    invert = request.form.get("invert") == "true"

    # Pipeline pesado (devuelve BGRA)
    img_bgra = procesar_pipeline_pesado(img_hash, img_bytes)

    # Separar canales CORRECTAMENTE
    b, g, r, a = cv2.split(img_bgra)
    img_bgr = cv2.merge([b, g, r])  # 🔥 sigue siendo BGR

    # Invertir colores si es necesario
    if invert:
        img_bgr = cv2.bitwise_not(img_bgr)
    # =========================
    # DITHER ACTIVADO
    # =========================
    if dither:
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        bias = threshold - 128
        gray_adj = cv2.convertScaleAbs(
            gray,
            alpha=contrast,
            beta=brightness - bias
        )

        h, w = gray_adj.shape

        if pixel_size > 1:
            sw, sh = max(1, w // pixel_size), max(1, h // pixel_size)
            gray_small = cv2.resize(gray_adj, (sw, sh), interpolation=cv2.INTER_LANCZOS4)
            dithered = jarvis_dither_fast(gray_small, 127)
            gray_final = cv2.resize(dithered, (w, h), interpolation=cv2.INTER_NEAREST)
        else:
            gray_final = jarvis_dither_fast(gray_adj, 127)

        final_bgr = cv2.cvtColor(
            gray_final.astype(np.uint8),
            cv2.COLOR_GRAY2BGR
        )

    # =========================
    # SIN DITHER (COLOR REAL)
    # =========================
    else:
        
        final_bgr = cv2.convertScaleAbs(
            img_bgr,
            alpha=contrast,
            beta=brightness
        )

    # =========================
    # UNIR ALFA Y CONVERTIR UNA SOLA VEZ
    # =========================
    final_bgra = cv2.merge([final_bgr[:, :, 0],
                            final_bgr[:, :, 1],
                            final_bgr[:, :, 2],
                            a])

    final_rgba = cv2.cvtColor(final_bgra, cv2.COLOR_BGRA2RGBA)

    _, buffer = cv2.imencode(".png", final_rgba)
    return send_file(io.BytesIO(buffer), mimetype="image/png")


# ================== RUTAS ==================
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/preview", methods=["POST"])
def preview_route():
    try: return process_logic()
    except Exception as e:
        log.error(f"Error Preview: {e}", exc_info=True)
        return {"error": str(e)}, 500

@app.route("/export", methods=["POST"])
def export_route():
    try: return process_logic()
    except Exception as e:
        log.error(f"Error Export: {e}")
        return {"error": str(e)}, 500

if __name__ == "__main__":
    log.info("Iniciando Flask en http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
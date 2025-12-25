/* =========================================
   ELEMENTOS DEL DOM Y CONFIGURACIÓN
   ========================================= */
const imageInput = document.getElementById("imageInput");
const canvas = document.getElementById("previewCanvas");
const ctx = canvas.getContext("2d");

let isProcessing = false; // Bloqueo de peticiones simultáneas

// Elementos de la Animación de Carga
const overlay = document.getElementById("loading-overlay");
const loadingText = document.getElementById("loading-text");
let statusInterval = null;

// --- NUEVA VARIABLE DE CONTROL ---
// Solo será true cuando el usuario suba un archivo nuevo
let isNewImage = false; 

const inputs = {
    brightness: document.getElementById("brightness"),
    contrast: document.getElementById("contrast"),
    invert: document.getElementById("invert"),
    dither: document.getElementById("dither"),
    threshold: document.getElementById("threshold"),
    pixel_size: document.getElementById("pixel_size")
};

const labels = {
    brightness: document.getElementById("brightnessValue"),
    contrast: document.getElementById("contrastValue"),
    threshold: document.getElementById("thresholdValue"),
    pixel_size: document.getElementById("pixelSizeValue")
};

const defaultValues = {
    brightness: 0,
    contrast: 1,
    threshold: 128,
    invert: false,
    dither: false,
    pixel_size: 2
};

let currentImage = null;
let debounceTimer = null;

/* =========================================
   LÓGICA DE ANIMACIÓN
   ========================================= */
const messages = [
    "Subiendo imagen a la nube...",
    "IA de ArtGuru analizando detalles...",
    "Mejorando nitidez y texturas...",
    "Eliminando fondo con precisión...",
    "Aplicando retoques finales...",
    "Generando vista previa..."
];

function startLoadingAnimation() {
    if (overlay) overlay.classList.remove('hidden');
    
    let step = 0;
    if (loadingText) loadingText.innerText = messages[0];

    if (statusInterval) clearInterval(statusInterval);

    statusInterval = setInterval(() => {
        step++;
        if (step < messages.length && loadingText) {
            loadingText.innerText = messages[step];
        }
    }, 4500);
}

function stopLoadingAnimation() {
    if (overlay) overlay.classList.add('hidden');
    if (statusInterval) clearInterval(statusInterval);
    if (loadingText) loadingText.innerText = "Iniciando...";
}

/* =========================================
   ACTUALIZAR ETIQUETAS VISUALES
   ========================================= */
function updateLabels() {
    labels.brightness.textContent = inputs.brightness.value + "%";
    labels.contrast.textContent = Math.round(inputs.contrast.value * 100) + "%";
    labels.threshold.textContent = Math.round((inputs.threshold.value / 255) * 100) + "%";
    
    if (labels.pixel_size) {
        labels.pixel_size.textContent = inputs.pixel_size.value;
    }
}

/* =========================================
   ENVIAR DATOS AL SERVIDOR Y PREVIEW
   ========================================= */
function updatePreview() {
    if (!currentImage) return;

    // Si ya hay una petición volando, no enviamos otra.
    // Esto evita que el navegador aborte la conexión y tire ERR_FAILED.
    if (isProcessing) {
        console.warn("Petición en curso, ignorando cambio actual...");
        return;
    }

    isProcessing = true; // Iniciamos bloqueo

    if (isNewImage) {
        startLoadingAnimation();
    }

    const formData = new FormData();
    formData.append("image", currentImage);
    formData.append("brightness", inputs.brightness.value);
    formData.append("contrast", inputs.contrast.value);
    formData.append("invert", inputs.invert.checked);
    formData.append("dither", inputs.dither.checked);
    formData.append("threshold", inputs.threshold.value);
    formData.append("pixel_size", inputs.pixel_size.value);

    fetch("/preview", { method: "POST", body: formData })
        .then(res => {
            if (!res.ok) throw new Error("Servidor ocupado o error 500");
            return res.blob();
        })
        .then(blob => {
            const img = new Image();
            img.onload = () => {
                const targetWidth = 600;
                const targetHeight = 800;
                canvas.width = targetWidth;
                canvas.height = targetHeight;
                ctx.clearRect(0, 0, targetWidth, targetHeight);

                const scale = Math.min(targetWidth / img.width, targetHeight / img.height);
                const drawWidth = img.width * scale;
                const drawHeight = img.height * scale;
                const offsetX = (targetWidth - drawWidth) / 2;
                const offsetY = (targetHeight - drawHeight) / 2;

                ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
                URL.revokeObjectURL(img.src); // Limpieza de memoria
            };
            img.src = URL.createObjectURL(blob);
        })
        .catch(err => {
            console.error("Error en preview:", err);
            // Solo mostramos error si no es una cancelación normal
            if (isNewImage) alert("Error al conectar con la IA de ArtGuru.");
        })
        .finally(() => {
            stopLoadingAnimation();
            isNewImage = false; 
            isProcessing = false; // Liberamos el bloqueo para la siguiente petición
        });
}

function schedulePreview() {
    clearTimeout(debounceTimer);
    // Un poco más de tiempo para dar respiro al servidor
    debounceTimer = setTimeout(updatePreview, 300); 
}

/* =========================================
   ESCUCHA DE EVENTOS
   ========================================= */

// Al seleccionar una imagen nueva
imageInput.addEventListener("change", e => {
    if (e.target.files && e.target.files[0]) {
        currentImage = e.target.files[0];
        
        // --- AQUÍ ACTIVAMOS LA BANDERA ---
        // Decimos: "¡Oye, esto requerirá ArtGuru, prende la animación!"
        isNewImage = true; 
        
        updatePreview(); 
    }
});

// Al mover cualquier slider o checkbox
Object.values(inputs).forEach(input => {
    if (!input) return;
    input.addEventListener("input", () => {
        // AQUÍ NO tocamos isNewImage, así que sigue siendo false.
        updateLabels();
        schedulePreview();
    });
});

/* =========================================
   RESET DE VALORES INDIVIDUALES
   ========================================= */
document.querySelectorAll(".reset-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        const target = btn.dataset.target;
        const input = inputs[target];

        if (!input) return;

        if (input.type === "checkbox") {
            input.checked = defaultValues[target];
        } else {
            input.value = defaultValues[target];
        }

        updateLabels();
        schedulePreview();
    });
});

/* =========================================
   EXPORTACIÓN
   ========================================= */
document.getElementById("downloadBtn").addEventListener("click", () => {
    if (!currentImage) {
        alert("Por favor, sube una imagen primero.");
        return;
    }

    // Opcional: Para descargar sí suele gustar ver que "algo pasa",
    // pero si quieres quitarlo también aquí, borra la línea de abajo.
    startLoadingAnimation(); 

    const formData = new FormData();
    formData.append("image", currentImage);
    formData.append("brightness", inputs.brightness.value);
    formData.append("contrast", inputs.contrast.value);
    formData.append("invert", inputs.invert.checked);
    formData.append("dither", inputs.dither.checked);
    formData.append("threshold", inputs.threshold.value);
    formData.append("pixel_size", inputs.pixel_size.value);

    fetch("/export", { method: "POST", body: formData })
        .then(res => res.blob())
        .then(blob => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `cnc_export_${Date.now()}.png`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        })
        .catch(err => {
            console.error("Error en exportación:", err);
            alert("Error al descargar");
        })
        .finally(() => {
            stopLoadingAnimation();
        });
});

// Inicializar etiquetas
updateLabels();
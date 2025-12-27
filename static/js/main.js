/* =========================================
   ELEMENTOS DEL DOM Y CONFIGURACIÓN
   ========================================= */
const imageInput = document.getElementById("imageInput");
const imageSelect = document.getElementById("imageSelect");
const carouselInner = document.getElementById("carousel-inner");
const prevBtn = document.getElementById("prevBtn");
const nextBtn = document.getElementById("nextBtn");

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

let currentImages = [];
let settingsMap = {}; // {filename: {brightness:.., ...}}
let currentFilename = null;
let previousUrls = [];
let currentIndex = 0;
let totalSlides = 0;
let debounceTimer = null;

/* =========================================
   LÓGICA DE ANIMACIÓN
   ========================================= */
const messages = [
    "Subiendo imágenes a la nube...",
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
   CARGAR CONFIGURACIÓN A INPUTS
   ========================================= */
function loadSettingsToInputs() {
    const s = settingsMap[currentFilename];
    if (!s) return;

    inputs.brightness.value = s.brightness;
    inputs.contrast.value = s.contrast;
    inputs.invert.checked = s.invert;
    inputs.dither.checked = s.dither;
    inputs.threshold.value = s.threshold;
    inputs.pixel_size.value = s.pixel_size;

    updateLabels();
}

/* =========================================
   GUARDAR CONFIGURACIÓN DESDE INPUTS
   ========================================= */
function saveInputsToSettings() {
    if (!currentFilename) return;

    const s = settingsMap[currentFilename];
    s.brightness = parseInt(inputs.brightness.value);
    s.contrast = parseFloat(inputs.contrast.value);
    s.invert = inputs.invert.checked;
    s.dither = inputs.dither.checked;
    s.threshold = parseInt(inputs.threshold.value);
    s.pixel_size = parseInt(inputs.pixel_size.value);
}

/* =========================================
   MOSTRAR PREVIEWS EN CARRUSEL
   ========================================= */
function displayPreviews(previews) {
    // Revocar URLs anteriores para liberar memoria
    previousUrls.forEach(u => URL.revokeObjectURL(u));
    previousUrls = [];

    carouselInner.innerHTML = '';
    previews.forEach(p => {
        const item = document.createElement('div');
        item.className = 'carousel-item';
        
        const img = document.createElement('img');
        img.src = p.data;
        img.alt = p.filename;
        
        item.appendChild(img);
        carouselInner.appendChild(item);

        // Si es URL de blob, guardarla para revocar después
        if (!p.data.startsWith('data:')) {
            previousUrls.push(p.data);
        }
    });

    totalSlides = previews.length;
    showSlide(currentIndex);

    if (totalSlides > 1) {
        prevBtn.style.display = 'block';
        nextBtn.style.display = 'block';
    } else {
        prevBtn.style.display = 'none';
        nextBtn.style.display = 'none';
    }
}

function showSlide(index) {
    currentIndex = Math.max(0, Math.min(index, totalSlides - 1));
    carouselInner.style.transform = `translateX(-${currentIndex * 100}%)`;
}

/* =========================================
   ENVIAR DATOS AL SERVIDOR Y PREVIEW
   ========================================= */
function updatePreview() {
    if (currentImages.length === 0) return;

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
    currentImages.forEach(file => formData.append("image", file));

    const settings = {};
    currentImages.forEach(file => {
        settings[file.name] = { ...settingsMap[file.name] };
    });
    formData.append("settings", JSON.stringify(settings));

    fetch("/preview", { method: "POST", body: formData })
        .then(res => {
            if (!res.ok) throw new Error("Servidor ocupado o error 500");
            const contentType = res.headers.get('Content-Type');
            if (contentType.includes('application/json')) {
                return res.json().then(json => ({ type: 'json', data: json }));
            } else {
                return res.blob().then(blob => ({ type: 'blob', data: blob }));
            }
        })
        .then(result => {
            let previews = [];
            if (result.type === 'blob') {
                const url = URL.createObjectURL(result.data);
                previews = [{ filename: currentImages[0].name, data: url }];
            } else {
                previews = result.data.previews;
            }
            displayPreviews(previews);
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

// Al seleccionar imágenes nuevas
imageInput.addEventListener("change", e => {
    if (e.target.files && e.target.files.length > 0) {
        currentImages = Array.from(e.target.files);
        
        settingsMap = {};
        imageSelect.innerHTML = '';
        currentImages.forEach(file => {
            settingsMap[file.name] = { ...defaultValues };
            const opt = document.createElement('option');
            opt.value = file.name;
            opt.text = file.name;
            imageSelect.appendChild(opt);
        });

        if (currentImages.length > 0) {
            currentFilename = currentImages[0].name;
            imageSelect.value = currentFilename;
            loadSettingsToInputs();
        }

        if (currentImages.length <= 1) {
            imageSelect.parentElement.style.display = 'none';
        } else {
            imageSelect.parentElement.style.display = 'block';
        }

        // --- AQUÍ ACTIVAMOS LA BANDERA ---
        // Decimos: "¡Oye, esto requerirá ArtGuru, prende la animación!"
        isNewImage = true; 
        
        currentIndex = 0;
        updatePreview(); 
    }
});

// Selector de imagen
imageSelect.addEventListener("change", () => {
    currentFilename = imageSelect.value;
    loadSettingsToInputs();

    // Saltar al slide correspondiente
    const index = currentImages.findIndex(f => f.name === currentFilename);
    if (index !== -1) {
        currentIndex = index;
        showSlide(currentIndex);
    }
});

// Al mover cualquier slider o checkbox
Object.values(inputs).forEach(input => {
    if (!input) return;
    input.addEventListener("input", () => {
        // AQUÍ NO tocamos isNewImage, así que sigue siendo false.
        updateLabels();
        saveInputsToSettings();
        schedulePreview();
    });
});

// Controles del carrusel
prevBtn.addEventListener("click", () => {
    currentIndex = (currentIndex > 0) ? currentIndex - 1 : totalSlides - 1;
    showSlide(currentIndex);
    syncCarouselToSelect();
});

nextBtn.addEventListener("click", () => {
    currentIndex = (currentIndex < totalSlides - 1) ? currentIndex + 1 : 0;
    showSlide(currentIndex);
    syncCarouselToSelect();
});

function syncCarouselToSelect() {
    const file = currentImages[currentIndex];
    if (file) {
        currentFilename = file.name;
        imageSelect.value = currentFilename;
        loadSettingsToInputs();
    }
}

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
        saveInputsToSettings();
        schedulePreview();
    });
});

/* =========================================
   EXPORTACIÓN
   ========================================= */
document.getElementById("downloadBtn").addEventListener("click", () => {
    if (currentImages.length === 0) {
        alert("Por favor, sube una imagen primero.");
        return;
    }

    // Opcional: Para descargar sí suele gustar ver que "algo pasa",
    // pero si quieres quitarlo también aquí, borra la línea de abajo.
    startLoadingAnimation(); 

    const formData = new FormData();
    currentImages.forEach(file => formData.append("image", file));

    const settings = {};
    currentImages.forEach(file => {
        settings[file.name] = { ...settingsMap[file.name] };
    });
    formData.append("settings", JSON.stringify(settings));

    fetch("/export", { method: "POST", body: formData })
        .then(res => {
            if (!res.ok) throw new Error("Error en exportación");
            return res.blob().then(blob => ({
                blob,
                contentType: res.headers.get('Content-Type')
            }));
        })
        .then(({ blob, contentType }) => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            if (contentType.includes('image/png')) {
                a.download = `cnc_export_${Date.now()}.png`;
            } else if (contentType.includes('application/zip')) {
                a.download = `cnc_exports_${Date.now()}.zip`;
            }
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
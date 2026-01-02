import os

# Render siempre usa el puerto 10000 en instancias free
# Usamos directamente 10000, con fallback solo para pruebas locales

# Si quieres ser ultra explícito (recomendado para evitar dudas):
bind = "0.0.0.0:10000"

workers = 2
threads = 2
timeout = 120
graceful_timeout = 120
max_requests = 500
max_requests_jitter = 50

# Esto ayuda a que Render detecte más rápido el puerto
loglevel = "info"
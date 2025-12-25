# Usa una imagen ligera de Python
FROM python:3.10-slim

# Establece el directorio de trabajo
WORKDIR /app

# Copia los archivos necesarios
COPY requirements.txt .

# Instala las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código
COPY . .

# Exponer el puerto (Render usa variables de entorno, pero esto es buena práctica)
EXPOSE 5000

# Comando para correr la app usando Gunicorn
# "app:app" significa: del archivo app.py, busca el objeto 'app'
CMD ["sh", "-c", "gunicorn app:app \
  --bind 0.0.0.0:${PORT:-5000} \
  --workers 2 \
  --threads 2 \
  --timeout 120 \
  --graceful-timeout 120 \
  --max-requests 500 \
  --max-requests-jitter 50"]

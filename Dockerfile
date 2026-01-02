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

# Expone el puerto 10000
EXPOSE 10000

# Cambia el CMD a esto (más simple y fiable para Render)
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
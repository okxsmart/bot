# Базовий імедж
FROM python:3.10-slim

# Встановлення системних залежностей, включно з ffmpeg
RUN apt-get update && apt-get install -y \
    git \
    ffmpeg \
    build-essential \
    pkg-config \
    clang \
 && rm -rf /var/lib/apt/lists/*

# Копіювання файлів проєкту
COPY . .

# Встановлення Python-залежностей
RUN sed '/-e/d' requirements.txt | pip install -r /dev/stdin
RUN pip install -r requirements.txt

# Відкриття порту (можливо потрібно, якщо ти запускаєш Quart/FastAPI)
EXPOSE 8080

# Команда запуску
CMD ["python", "app.py"]

# Попередній крок (наприклад FROM python:3.10-slim)
FROM python:3.10-slim

# Встановлення залежностей ОС, включно з git
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    pkg-config \
    clang \
 && rm -rf /var/lib/apt/lists/*

# Копіювання файлів проєкту
COPY . .

# Встановлення Python-залежностей
RUN sed '/-e/d' requirements.txt | pip install -r /dev/stdin
RUN pip install -r requirements.txt

# Відкриття порту
EXPOSE 8080

# Запуск
CMD ["python", "app.py"]

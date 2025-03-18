FROM python:3.8.10-slim AS build

WORKDIR /app

RUN apt-get update && apt-get install -y git

RUN git clone --depth 1 https://github.com/pixelite1201/BEDLAM.git /app/BEDLAM

COPY requirements.txt .

RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
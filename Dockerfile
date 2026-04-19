FROM python:3.11-slim

WORKDIR /app

# تحديث pip أولاً
RUN pip install --upgrade pip

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "bot_factory.py"]
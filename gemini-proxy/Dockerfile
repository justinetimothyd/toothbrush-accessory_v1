FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY gemini_proxy.py .

EXPOSE 8080

CMD ["python", "gemini_proxy.py"]

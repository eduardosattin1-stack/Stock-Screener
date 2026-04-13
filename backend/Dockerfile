FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY screener_v6.py .
COPY run_server.py .
CMD ["python", "run_server.py"]

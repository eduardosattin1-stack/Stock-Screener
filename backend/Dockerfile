FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY screener_v6.py .
COPY run_server.py .
COPY backtest_full.py .
COPY backtest_time.py .
COPY macro_regime.py .
COPY monitor_v7.py .
COPY weekly_report.py .
COPY run_time_job.py .
CMD ["python", "run_server.py"]
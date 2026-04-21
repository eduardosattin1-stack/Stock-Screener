FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# v8.1: copy all .py files plus the ML model, instead of an explicit COPY
# list. Prevents the category of bugs where new modules (factor_8k_catalyst,
# factor_etf_flow_velocity, backtest_safety_stubs) get added to the repo
# but forgotten in the Dockerfile, silently leaving them out of the image.
COPY *.py ./
COPY time_model_10pct.pkl ./

CMD ["python", "run_server.py"]

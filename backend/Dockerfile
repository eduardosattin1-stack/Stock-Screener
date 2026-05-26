FROM python:3.12-slim

# libgomp1: required by xgboost + lightgbm C runtime (OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# v8.1: copy all .py files plus the ML model, instead of an explicit COPY
# list. Prevents the category of bugs where new modules (factor_8k_catalyst,
# factor_etf_flow_velocity, backtest_safety_stubs) get added to the repo
# but forgotten in the Dockerfile, silently leaving them out of the image.
COPY *.py ./
COPY strategy_allowlists/ ./strategy_allowlists/
COPY alpha_compounder/ ./alpha_compounder/
COPY time_model_v2.pkl time_model_v3.pkl ./
CMD ["python", "run_server.py"]

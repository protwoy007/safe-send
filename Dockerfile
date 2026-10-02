# ---- stage 1: build the React frontend (skipped automatically if frontend/ does not exist yet)
FROM node:20-slim AS web
WORKDIR /repo
COPY . .
ENV VITE_API_URL=""
RUN mkdir -p /repo/frontend/dist && \
    if [ -f frontend/package.json ]; then cd frontend && npm ci && npm run build; fi

# ---- stage 2: Python API (+ built frontend), data and model generated at build time
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=user src ./src
COPY --chown=user scripts ./scripts
COPY --chown=user --from=web /repo/frontend/dist ./frontend/dist

# deterministic synthetic data + features + trained model (seed 42), no personal data involved
RUN python -m src.data_gen.generate --out data --seed 42 > /dev/null && \
    python -m src.features.build --data data --out data/features.csv && \
    python -m src.models.train --data data > /dev/null

ENV DATA_DIR=data MODEL_PATH=models/risk_model.pkl FRONTEND_DIST=frontend/dist
# INVESTIGATOR_API_KEY must be provided as a secret at run time (never baked into the image)
EXPOSE 7860
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]

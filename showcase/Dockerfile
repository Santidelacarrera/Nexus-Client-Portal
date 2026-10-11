# NO PROBADO en este repositorio (el entorno de desarrollo no tenía Docker). Revísalo antes de usarlo.
FROM node:22-slim AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tailwind.config.js ./
COPY scripts ./scripts
COPY src ./src
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src ./src
COPY content ./content
COPY --from=assets /app/src/static ./src/static
USER 10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "--factory", "src.main:app_factory", "--no-server-header", "--host", "0.0.0.0", "--port", "8000"]

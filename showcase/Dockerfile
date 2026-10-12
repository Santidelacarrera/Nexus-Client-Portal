# Nexus Security & AI Lab — vitrina comercial.
# Construcción normal:   docker build -t nexus-showcase .
# Detrás de un proxy que inspecciona TLS (CA propia), sin hornear la CA en la imagen:
#   docker build --secret id=ca,src=/ruta/ca-bundle.crt -t nexus-showcase .
ARG NODE_IMAGE=node:22-slim
ARG PYTHON_IMAGE=python:3.13-slim

FROM ${NODE_IMAGE} AS assets
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=secret,id=ca,required=false sh -c '[ -f /run/secrets/ca ] && export NODE_EXTRA_CA_CERTS=/run/secrets/ca; npm ci'
COPY tailwind.config.js ./
COPY scripts ./scripts
COPY src ./src
RUN npm run build

FROM ${PYTHON_IMAGE}
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --system --uid 10001 --no-create-home app
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=secret,id=ca,required=false sh -c '[ -f /run/secrets/ca ] && export PIP_CERT=/run/secrets/ca; pip install --no-cache-dir -r requirements.txt'
COPY src ./src
COPY content ./content
COPY --from=assets /app/src/static ./src/static
USER 10001
LABEL org.opencontainers.image.title="Nexus Security & AI Lab - showcase"
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "--factory", "src.main:app_factory", "--no-server-header", "--host", "0.0.0.0", "--port", "8000"]

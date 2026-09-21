# Bau aus der Projektwurzel:  docker build -t opel-bridge .
# Die Bridge braucht nur die Python-Standardbibliothek.
FROM python:3.12-alpine

WORKDIR /app
COPY bridge/opelbridge/ ./bridge/opelbridge/
COPY bridge/config.example.json ./bridge/config.example.json
COPY tools/preview.html ./tools/preview.html
COPY watchapp/entry/src/main/js/default/common/util.js ./watchapp/entry/src/main/js/default/common/util.js

WORKDIR /app/bridge
ENV OPELBRIDGE_HOST=0.0.0.0 \
    OPELBRIDGE_PORT=8787 \
    PYTHONUNBUFFERED=1

EXPOSE 8787
VOLUME ["/data"]

HEALTHCHECK --interval=60s --timeout=5s \
  CMD wget -qO- http://127.0.0.1:8787/health || exit 1

CMD ["python", "-m", "opelbridge", "--config", "/data/config.json"]

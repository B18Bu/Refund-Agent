FROM node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293 AS frontend-build
WORKDIR /frontend
COPY frontend/package.json ./
RUN npm install --registry=https://registry.npmjs.org --fetch-retries=10 --fetch-retry-mintimeout=1000 --fetch-retry-maxtimeout=60000 --fetch-timeout=300000
COPY frontend ./
RUN npm run build

FROM redis/redis-stack-server:latest AS redis-stack

FROM pgvector/pgvector:pg15
ENV DEBIAN_FRONTEND=noninteractive PGDATA=/var/lib/postgresql/data PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl nginx python3 python3-pip python3-venv redis-server supervisor libgomp1 libglib2.0-0 libgl1 \
 && python3 -m venv /opt/venv \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements-ocr.txt backend/requirements-rag-embedding.txt ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --retries 10 --timeout 60 -i https://pypi.org/simple setuptools \
 && pip install --retries 10 --timeout 60 -i https://pypi.org/simple -r requirements.txt \
 && pip install --retries 10 --timeout 60 -i https://pypi.org/simple -r requirements-ocr.txt \
 && curl --fail --location --retry 10 --retry-all-errors --continue-at - --output /tmp/torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl "https://download-r2.pytorch.org/whl/cpu/torch-2.6.0%2Bcpu-cp311-cp311-linux_x86_64.whl" \
 && echo "5b6ae523bfb67088a17ca7734d131548a2e60346c622621e4248ed09dd0790cc  /tmp/torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl" | sha256sum -c - \
 && pip install --retries 10 --timeout 60 -i https://pypi.org/simple /tmp/torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl \
 && rm /tmp/torch-2.6.0+cpu-cp311-cp311-linux_x86_64.whl \
 && pip install --retries 10 --timeout 60 -i https://pypi.org/simple -r requirements-rag-embedding.txt \
 && pip install --retries 10 --timeout 60 -i https://pypi.org/simple "ml-dtypes<0.6"
COPY backend ./
COPY scripts ./scripts
COPY evals ./evals
COPY deploy /deploy
COPY scripts /scripts
COPY evals /evals
COPY frontend/nginx.conf /frontend/nginx.conf
COPY --from=frontend-build /frontend/dist /usr/share/nginx/html
COPY --from=redis-stack /opt/redis-stack /opt/redis-stack
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/single-container/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY deploy/single-container/supervisord.conf /etc/supervisor/conf.d/app.conf
RUN chmod 755 /usr/local/bin/entrypoint.sh \
 && rm -f /etc/nginx/sites-enabled/default \
 && mkdir -p /data/uploads /var/lib/redis \
 && chown -R postgres:postgres /var/lib/postgresql \
 && chown -R redis:redis /var/lib/redis
EXPOSE 80
VOLUME ["/var/lib/postgresql/data", "/var/lib/redis", "/data/uploads"]
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

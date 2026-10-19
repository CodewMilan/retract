FROM node:22-bookworm-slim AS landing
WORKDIR /src/landing
COPY landing/package.json landing/package-lock.json ./
RUN npm ci
COPY landing ./
COPY docs /src/docs
COPY examples /src/examples
COPY README.md THIRD_PARTY_NOTICES.md /src/
# landing/src/Account.jsx imports ../../src/retract/web/loader.mjs, which is /src/src/... here.
COPY src/retract/web/loader.mjs /src/src/retract/web/loader.mjs
RUN npm run build

FROM python:3.12-slim-bookworm AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY src ./src
COPY --from=landing /src/landing/dist ./src/retract/site
RUN pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock && \
    groupadd --gid 10001 retract && useradd --uid 10001 --gid retract --no-create-home retract
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/*.whl && rm -rf /wheels
USER retract
EXPOSE 8100
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT',os.getenv('RETRACT_PORT','8100'))+'/health',timeout=3)"
CMD ["retract", "serve"]

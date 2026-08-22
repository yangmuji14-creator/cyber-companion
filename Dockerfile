FROM python:3.12-slim

ARG INSTALL_EXTRAS=""

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY core ./core
COPY adapters ./adapters
COPY mcp_servers ./mcp_servers
COPY plugins ./plugins
COPY tools ./tools
COPY webui ./webui
COPY main.py setup_wizard.py install.py import_chat.py import_exskill.py ./
COPY config/*.example.json /opt/mu/default-config/
COPY docker-entrypoint.sh /usr/local/bin/mu-entrypoint

RUN if [ -n "$INSTALL_EXTRAS" ]; then \
      pip install ".[${INSTALL_EXTRAS}]"; \
    else \
      pip install .; \
    fi \
    && chmod +x /usr/local/bin/mu-entrypoint

EXPOSE 8000

ENV CC_WEB_HOST=0.0.0.0 \
    CC_WEB_PORT=8000

ENTRYPOINT ["mu-entrypoint"]
CMD ["python", "main.py", "web"]

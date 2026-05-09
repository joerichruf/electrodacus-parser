FROM python:3.13-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE /app/
COPY src /app/src

RUN python -m pip install --no-cache-dir -e . \
 && useradd --no-create-home --uid 10001 sbms
USER sbms

ENTRYPOINT ["electrodacus-parser"]
CMD ["--help"]

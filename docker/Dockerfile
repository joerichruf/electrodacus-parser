FROM python:3.13-slim

WORKDIR /app

# Install the project
COPY pyproject.toml README.md /app/
COPY src /app/src

RUN python -m pip install --no-cache-dir -e .

ENTRYPOINT ["electrodacus-parser"]
CMD ["--help"]

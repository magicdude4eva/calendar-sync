FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# All dependencies ship prebuilt wheels for amd64 and arm64, so no compiler
# toolchain is needed (keeps the image small and multi-arch builds fast).
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ src/

# Pass arguments like --import, --cleanup or --dry-run to the container
ENTRYPOINT ["python", "src/calendar_sync.py"]

# syntax=docker/dockerfile:1
#
# Build listing from local source -- no PyPI publish in the deploy path.
#   podman build -t dynamicalsystem/listing .
#
# Debian slim (not alpine): manylinux wheels exist for lxml/pydantic-core,
# so the build needs no compiler toolchain.
FROM python:3.13-slim

WORKDIR /app

# Install the package from the working tree. hatchling builds it in an
# isolated, discarded build env, so no build tooling lingers in the image.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# SQLite state lives on a mounted volume; config arrives via env.
# Empty LISTING_LOG_FILE = log to stdout for journald (the on-disk default
# is /var/log/listing/daily.log, which does not exist in the container).
ENV LISTING_DB_PATH=/data/listing.db \
    LISTING_LOG_FILE=
RUN mkdir -p /data
VOLUME ["/data"]

# Long-lived web service by default; the one-shot maintenance sweep is
#   podman run <img> python -m dynamicalsystem.listing.maintenance.daily
# Timing is systemd's job (tinsnip listing-maintain.timer), not the image.
EXPOSE 8000
CMD ["uvicorn", "dynamicalsystem.listing.webserver.main:app", "--host", "0.0.0.0", "--port", "8000"]

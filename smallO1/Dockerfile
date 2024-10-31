FROM python:3.11-slim-bullseye

RUN --mount=type=cache,target=var/cache/apt/archives apt-get update && apt-get install --no-install-recommends -y \
  supervisor \
  # dependencies for building Python packages
  build-essential \
  # handy tolls
  wget

WORKDIR /app/dependencies
COPY . .
RUN --mount=type=cache,target=/root/.cache/pip/ pip install .
WORKDIR /app
RUN rm -rf /app/dependencies

ENV working_dir=/app

CMD ["small-o1"]

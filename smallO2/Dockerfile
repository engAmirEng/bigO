FROM golang:1.24-alpine3.22 AS builder

# setup smallO2 binay
WORKDIR /app
# Copy go.mod and go.sum first for dependency caching
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the application code
COPY . .

# Build the Go binary
RUN CGO_ENABLED=0 go build -ldflags="-s -w" -o myapp ./...

# --- Stage 2: Run the Go app ---
FROM python:3.13.6-slim-bullseye

# Install CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    # integration binaries \
    nginx \
    haproxy \
    wireguard \
    # handy dependencies
    openssh-server \
    openssh-client \
    sshpass \
    # handy tools
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# setting up supervisor
RUN pip install supervisor==4.3.0
RUN mkdir /etc/supervisor/
RUN mkdir /var/log/supervisor
RUN cat <<'EOF' > /etc/supervisor/supervisord.conf
[unix_http_server]
file=/var/run/supervisor.sock
chmod=0700

[supervisord]
logfile=/var/log/supervisor/supervisord.log
pidfile=/var/run/supervisord.pid
childlogdir=/var/log/supervisor

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix:///var/run/supervisor.sock

[include]
files = /app/workdir/supervisor/supervisor.conf
EOF

# Set working directory
WORKDIR /app

# Copy the built binary from the builder
COPY --from=builder /app/myapp .

RUN touch config.toml
RUN mkdir /app/workdir
ENV working_dir=/app/workdir
ENV full_control_supervisord=True
ENV supervisor_base_config_path=/etc/supervisor/supervisord.conf

# Preget some binary content
RUN --mount=type=secret,id=pre_api_key \
    --mount=type=secret,id=pre_sync_url \
    pre_api_key=$(cat /run/secrets/pre_api_key) && \
    pre_sync_url=$(cat /run/secrets/pre_sync_url) && \
    if [ -n "$pre_api_key" ] && [ -n "$pre_sync_url" ]; then \
      echo "Running pre_sync with API_KEY=[hidden] and URL=$pre_sync_url"; \
      api_key=$pre_api_key interval_sec=1 sync_url=$pre_sync_url ./myapp pre_run --config ./config.toml; \
      rm -rf workdir/logs/ workdir/supervisor/ workdir/conf/ workdir/sync_request.txt; \
    else \
      echo "Skipping pre_sync (missing secrets)"; \
    fi
# Start the app
CMD ["./myapp", "--config", "./config.toml"]

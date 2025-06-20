# Copy go.mod and go.sum first for dependency caching
COPY go.mod go.sum ./
RUN go mod download

# Copy the rest of the application code
COPY . .

# Build the Go binary
RUN go build -o myapp ./...

# --- Stage 2: Run the Go app ---
FROM debian:bullseye-slim

# Install CA certificates
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    supervisor \
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

WORKDIR /app/dependencies
# integration binaries
RUN wget https://dl.influxdata.com/telegraf/releases/telegraf-1.33.1_linux_amd64.tar.gz
RUN tar -xzvf telegraf-1.33.1_linux_amd64.tar.gz && cp telegraf-1.33.1/usr/bin/telegraf /usr/local/bin/telegraf && chmod +x /usr/local/bin/telegraf

# cleaning up
RUN rm -rf /app/dependencies

# Set working directory
WORKDIR /app

# Copy the built binary from the builder
COPY --from=builder /app/myapp .

RUN touch config.toml
RUN mkdir /app/workdir
ENV working_dir=/app/workdir
ENV full_control_supervisord=True
ENV supervisor_base_config_path=/etc/supervisor/supervisord.conf

# Start the app
CMD ["./myapp", "--config", "./config.toml"]

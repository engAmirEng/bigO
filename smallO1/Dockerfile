FROM python:3.11-slim-bullseye

RUN --mount=type=cache,target=var/cache/apt/archives apt-get update && apt-get install --no-install-recommends -y \
    supervisor \
    # integration binaries \
    nginx \
    # handy dependencies
    openssh-server \
    openssh-client \
    sshpass \
    # dependencies for building Python packages
    build-essential \
    # handy tolls
    wget

WORKDIR /app/dependencies
# integration binaries
RUN wget https://dl.influxdata.com/telegraf/releases/telegraf-1.33.1_linux_amd64.tar.gz
RUN tar -xzvf telegraf-1.33.1_linux_amd64.tar.gz && cp telegraf-1.33.1/usr/bin/telegraf /usr/local/bin/telegraf && chmod +x /usr/local/bin/telegraf

# installing core
COPY . .
RUN --mount=type=cache,target=/root/.cache/pip/ pip install .
WORKDIR /app

# cleaning up
RUN rm -rf /app/dependencies

ENV working_dir=/app
ENV full_control_supervisord=True

CMD ["small-o1"]

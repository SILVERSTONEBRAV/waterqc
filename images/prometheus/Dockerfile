FROM alpine:3.20

RUN apk add --no-cache \
    ca-certificates \
    wget \
    tar

ARG PROM_VERSION=2.54.1

RUN wget https://github.com/prometheus/prometheus/releases/download/v${PROM_VERSION}/prometheus-${PROM_VERSION}.linux-amd64.tar.gz \
 && tar -xzf prometheus-*.tar.gz \
 && mv prometheus-*/prometheus /usr/local/bin/ \
 && mv prometheus-*/promtool /usr/local/bin/ \
 && rm -rf prometheus-*

RUN addgroup -S prometheus && adduser -S prometheus -G prometheus

USER prometheus

EXPOSE 9090

CMD ["prometheus", "--config.file=/etc/prometheus/prometheus.yml", "--storage.tsdb.path=/prometheus"]

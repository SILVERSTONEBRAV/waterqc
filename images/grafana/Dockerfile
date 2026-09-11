FROM alpine:3.20

RUN apk add --no-cache \
    ca-certificates \
    bash \
    curl \
    tar

ARG GRAFANA_VERSION=11.0.0

RUN curl -L https://dl.grafana.com/oss/release/grafana-${GRAFANA_VERSION}.linux-amd64.tar.gz \
    -o grafana.tar.gz \
 && tar -xzf grafana.tar.gz \
 && mv grafana-* /usr/share/grafana \
 && rm grafana.tar.gz

RUN addgroup -S grafana && adduser -S grafana -G grafana

USER grafana

WORKDIR /usr/share/grafana

EXPOSE 3000

CMD ["./bin/grafana-server", "--homepath=/usr/share/grafana"]

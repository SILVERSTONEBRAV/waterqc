FROM alpine:3.20

RUN apk add --no-cache \
    ca-certificates \
    bash \
    curl \
    tar

ARG ETCD_VERSION=v3.5.12

RUN curl -L https://github.com/etcd-io/etcd/releases/download/${ETCD_VERSION}/etcd-${ETCD_VERSION}-linux-amd64.tar.gz \
    -o /tmp/etcd.tar.gz \
 && tar -xzf /tmp/etcd.tar.gz -C /usr/local/bin --strip-components=1 \
 && rm -rf /tmp/*

RUN addgroup -S etcd && adduser -S etcd -G etcd

USER etcd

EXPOSE 2379 2380

ENTRYPOINT ["etcd"]

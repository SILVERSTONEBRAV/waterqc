FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pgbouncer \
    ca-certificates \
    bash \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/pgbouncer

COPY pgbouncer.ini /etc/pgbouncer/pgbouncer.ini
COPY userlist.txt /etc/pgbouncer/userlist.txt

EXPOSE 6432

CMD ["pgbouncer", "/etc/pgbouncer/pgbouncer.ini"]
FROM caddy:builder AS builder

RUN xcaddy build \
    --with github.com/caddy-dns/acmedns

FROM cgr.dev/chainguard/static:latest

COPY --from=builder /usr/bin/caddy /usr/bin/caddy

ENTRYPOINT [ "caddy" ]

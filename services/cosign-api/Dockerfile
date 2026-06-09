# cosign-api — multi-stage Go build -> distroless static (non-root, ~static binary).
FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
ARG VERSION=dev
ARG COMMIT=none
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags "-s -w -X main.version=${VERSION} -X main.commit=${COMMIT}" \
    -o /cosign-api ./cmd/cosign-api

FROM gcr.io/distroless/static-debian12:nonroot
LABEL org.opencontainers.image.title="cosign-api" \
      org.opencontainers.image.source="https://github.com/tensor-bloom/cosign"
COPY --from=build /cosign-api /cosign-api
EXPOSE 8080 50051
USER nonroot:nonroot
ENTRYPOINT ["/cosign-api"]
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD ["/cosign-api", "healthcheck"]

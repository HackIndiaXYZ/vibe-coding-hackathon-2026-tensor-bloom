"""Environment configuration for cosign-worker."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # HTTP (health/metrics) + gRPC
    http_host: str
    http_port: int
    grpc_listen_addr: str
    # api identity gRPC (worker -> api)
    api_grpc_addr: str
    # stores
    database_url: str
    redis_url: str
    # sandbox
    sandbox_driver: str
    sandbox_image: str
    sandbox_network: str
    # llm routing config path
    routing_config_path: str
    # logging
    log_level: str

    @staticmethod
    def load() -> "Config":
        return Config(
            http_host=os.getenv("WORKER_HTTP_HOST", "0.0.0.0"),
            http_port=int(os.getenv("WORKER_HTTP_PORT", "8001")),
            # IPv4 bind: Docker bridge containers often have IPv6 disabled, so
            # "[::]" (IPv6 any) fails to bind inside the container.
            grpc_listen_addr=os.getenv("WORKER_GRPC_LISTEN_ADDR", "0.0.0.0:50052"),
            api_grpc_addr=os.getenv("API_GRPC_ADDR", "cosign-api:50051"),
            database_url=os.getenv(
                "DATABASE_URL", "postgres://cosign:changeme@postgres:5432/cosign"
            ),
            redis_url=os.getenv("REDIS_URL", "redis://redis:6379"),
            sandbox_driver=os.getenv("SANDBOX_DRIVER", "docker"),
            sandbox_image=os.getenv("SANDBOX_IMAGE", "cosign/sandbox:latest"),
            sandbox_network=os.getenv("SANDBOX_NETWORK", "cosign_sandbox_net"),
            routing_config_path=os.getenv(
                "LLM_ROUTING_CONFIG", "config/llm-routing.yaml"
            ),
            log_level=os.getenv("LOG_LEVEL", "info"),
        )

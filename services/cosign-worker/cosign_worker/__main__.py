"""cosign-worker entrypoint: FastAPI (/health, /metrics) + async gRPC server."""

from __future__ import annotations

import asyncio

import grpc
import redis.asyncio as aioredis
import structlog
import uvicorn
from fastapi import FastAPI

from .config import Config
from .context import WorkerContext
from .db.pool import create_pool
from .llm.router import LLMRouter, load_routing_config
from .orchestration.events import EventPublisher
from .sandbox.docker_driver import DockerDriver
from .tools.identity_client import IdentityClient

log = structlog.get_logger(__name__)


def build_app(ctx: WorkerContext) -> FastAPI:
    app = FastAPI(title="cosign-worker")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": "cosign-worker"}

    return app


async def serve_grpc(ctx: WorkerContext) -> grpc.aio.Server:
    # Imported lazily so the module loads even before pb is generated.
    from .rpc.pb import orchestration_pb2_grpc as pb2_grpc
    from .rpc.server import OrchestrationServicer

    server = grpc.aio.server()
    pb2_grpc.add_OrchestrationServiceServicer_to_server(OrchestrationServicer(ctx), server)
    server.add_insecure_port(ctx.config.grpc_listen_addr)
    await server.start()
    log.info("grpc orchestration listening", addr=ctx.config.grpc_listen_addr)
    return server


async def main() -> None:
    cfg = Config.load()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            {"debug": 10, "info": 20, "warn": 30, "error": 40}.get(cfg.log_level, 20)
        )
    )

    pool = await create_pool(cfg.database_url)
    redis = aioredis.from_url(cfg.redis_url, decode_responses=True)
    routing = load_routing_config(cfg.routing_config_path)
    router = LLMRouter(routing, pool=pool, redis=redis)
    sandbox = DockerDriver(image=cfg.sandbox_image, network=cfg.sandbox_network)
    identity = IdentityClient(cfg.api_grpc_addr)

    ctx = WorkerContext(
        config=cfg, pool=pool, redis=redis, router=router, sandbox=sandbox,
        identity=identity, events=EventPublisher(redis),
    )

    # Wire ctx.run_goal / resume_goal / cancel_goal (compiles the LangGraph).
    from .orchestration.graph import attach_orchestration

    await attach_orchestration(ctx)

    grpc_server = await serve_grpc(ctx)

    app = build_app(ctx)
    uconfig = uvicorn.Config(app, host=cfg.http_host, port=cfg.http_port, log_level=cfg.log_level)
    userver = uvicorn.Server(uconfig)

    async def _run_http() -> None:
        await userver.serve()

    http_task = asyncio.create_task(_run_http())
    log.info("cosign-worker up", http_port=cfg.http_port, grpc=cfg.grpc_listen_addr)

    try:
        await http_task
    finally:
        await grpc_server.stop(grace=5)
        await sandbox.close()
        await identity.close()
        await redis.aclose()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())

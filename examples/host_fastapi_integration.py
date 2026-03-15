from __future__ import annotations

from fastapi import FastAPI

from customer_ai_runtime.integration import CustomerAIRuntimeModule

host_app = FastAPI(title="Host Business System")
customer_ai_module = CustomerAIRuntimeModule.create()
customer_ai_module.mount_to(host_app, prefix="/customer-ai")


@host_app.get("/host-healthz")
async def host_healthz() -> dict[str, str]:
    return {"status": "ok"}

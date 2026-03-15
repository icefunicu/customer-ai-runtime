from customer_ai_runtime.app import create_app
from customer_ai_runtime.core.config import get_settings


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        create_app(),
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()

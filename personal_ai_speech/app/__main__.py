"""Start the speech server."""

import uvicorn

from .settings import load_settings


def main() -> None:
    """Run uvicorn with the add-on's settings."""
    settings = load_settings()
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104 - must listen on all interfaces inside the add-on container
        port=settings.port,
        log_level=settings.log_level,
        access_log=settings.log_level == "debug",
    )


if __name__ == "__main__":
    main()

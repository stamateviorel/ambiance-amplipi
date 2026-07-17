"""uvicorn entrypoint for ambiance-amplipi: `python -m ambiance.asgi` (or via systemd)."""
import uvicorn

from .app import app, cfg


def main():
    uvicorn.run(app, host="0.0.0.0", port=cfg.port, log_level="info")


if __name__ == "__main__":
    main()

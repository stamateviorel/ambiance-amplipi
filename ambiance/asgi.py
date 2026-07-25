"""uvicorn entrypoint for ambiance-amplipi: `python -m ambiance.asgi` (or via systemd)."""
import uvicorn

from .app import app, cfg


def main():
    # access_log=False: the openHAB binding + the display poll /api/status and /api/cover
    # every 1-3s; logging every request drowned the journal (~600k lines) and buried the real
    # events. Startup/error logs and the app's own print()s still go to the journal.
    uvicorn.run(app, host="0.0.0.0", port=cfg.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()

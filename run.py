from pathlib import Path

import uvicorn

from licmgr.httpserver.server import create_app


def run():
    app = create_app()
    log_config = Path(__file__).with_name("logging.json")
    uvicorn.run(app, log_config=str(log_config))


if __name__ == "__main__":
    raise SystemExit(run())

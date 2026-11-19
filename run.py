import uvicorn

from licmgr.httpserver.server import create_app


def run():
    app = create_app()
    uvicorn.run(app)


if __name__ == "__main__":
    raise SystemExit(run())

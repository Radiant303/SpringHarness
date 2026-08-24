import uvicorn

from spring_harness.core.services.web_server import run_web_server


def main() -> None:
    app = run_web_server()
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()

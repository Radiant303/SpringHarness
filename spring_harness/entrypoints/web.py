import threading
import webbrowser
from pathlib import Path

import uvicorn

from spring_harness.core.services.web_server import run_web_server

HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
    run_dir = Path.cwd()
    app = run_web_server(run_dir)
    threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()

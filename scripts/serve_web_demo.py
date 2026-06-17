from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_DEMO = ROOT / "web-demo"


def main() -> int:
    handler = partial(SimpleHTTPRequestHandler, directory=str(WEB_DEMO))
    server = ThreadingHTTPServer(("127.0.0.1", 8765), handler)
    print("Web Demo: http://127.0.0.1:8765")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Web Demo.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

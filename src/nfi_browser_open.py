# -*- coding: utf-8 -*-
"""Browser-openable URLs for local Jupyter and Google Colab.

Colab blocks file:// links from the notebook origin. Serve files over a local
HTTP port and resolve the Colab proxy URL so target=_blank / IFrame work.
"""

from __future__ import annotations

import html
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple, Union

PathLike = Union[str, Path]
LinkItem = Tuple[str, PathLike]

_STATE: dict = {"httpd": None, "port": None, "root": None}


def in_colab() -> bool:
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def ensure_http_root(root: PathLike) -> int:
    """Serve ``root`` on a background HTTP server; return the port."""
    root_p = Path(root).resolve()
    if _STATE["httpd"] is not None and _STATE["root"] == str(root_p):
        return int(_STATE["port"])

    if _STATE["httpd"] is not None:
        try:
            _STATE["httpd"].shutdown()
        except Exception:
            pass
        _STATE.update(httpd=None, port=None, root=None)

    port = _free_port()

    class _Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root_p), **kwargs)

        def log_message(self, format, *args):  # noqa: A003
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    _STATE.update(httpd=httpd, port=port, root=str(root_p))
    return port


def browser_url(path: PathLike, serve_root: Optional[PathLike] = None) -> str:
    """Return a URL the browser can open (file:// locally; Colab HTTPS proxy)."""
    path_p = Path(path).resolve()
    if not path_p.exists():
        raise FileNotFoundError(path_p)

    if not in_colab():
        return path_p.as_uri()

    root_p = Path(serve_root).resolve() if serve_root is not None else path_p.parent
    try:
        rel = path_p.relative_to(root_p).as_posix()
    except ValueError:
        root_p = path_p.parent
        rel = path_p.name

    port = ensure_http_root(root_p)
    from google.colab.output import eval_js

    base = eval_js(f"google.colab.kernel.proxyPort({int(port)})")
    return f"{str(base).rstrip('/')}/{rel}"


def deliverable_links_html(
    items: Sequence[LinkItem],
    *,
    serve_root: PathLike,
    title: str = "Open national HTML deliverables",
) -> str:
    """Build green open-in-new-tab buttons (Colab-safe)."""
    root_p = Path(serve_root).resolve()
    bits = [
        '<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif;line-height:1.5">',
        f'<h3 style="color:#1b5e20;margin:0 0 8px">{html.escape(title)}</h3>',
    ]
    if in_colab():
        bits.append(
            '<p style="margin:0 0 10px;color:#333;font-size:13px">'
            "Colab cannot open <code>file://</code> paths. Links below use an HTTP "
            "proxy so they open in a real browser tab.</p>"
        )

    for label, path in items:
        path_p = Path(path)
        if not path_p.exists() or path_p.suffix.lower() not in {".html", ".htm"}:
            continue
        try:
            href = browser_url(path_p, serve_root=root_p)
        except Exception as exc:
            bits.append(
                f'<p style="margin:8px 0;color:#b71c1c"><b>{html.escape(label)}</b> — '
                f"could not build open URL ({html.escape(str(exc))}). "
                f"Download from the Files pane: <code>{html.escape(str(path_p))}</code></p>"
            )
            continue
        bits.append(
            f'<p style="margin:8px 0"><a style="display:inline-block;padding:10px 14px;'
            f"background:#14351c;color:#fff;text-decoration:none;border-radius:8px;"
            f'font-weight:600" href="{html.escape(href, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(label)}</a>'
            f'<br/><code style="font-size:12px">{html.escape(str(path_p))}</code></p>'
        )
    bits.append("</div>")
    return "".join(bits)


def iframe_src(path: PathLike, serve_root: Optional[PathLike] = None) -> str:
    """URL suitable for ``IPython.display.IFrame``."""
    return browser_url(path, serve_root=serve_root)

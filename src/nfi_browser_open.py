# -*- coding: utf-8 -*-
"""Open HTML deliverables in an external browser tab (never inside the .ipynb).

Colab blocks ``file://`` links from the notebook origin. Working approach:
serve files over HTTP on the kernel, resolve ``google.colab.kernel.proxyPort``,
then show plain ``target=_blank`` links (button + URL text) in cell output.
"""

from __future__ import annotations

import html
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional, Sequence, Tuple, Union

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


def _rel_under(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def browser_url(path: PathLike, serve_root: Optional[PathLike] = None) -> str:
    """Return a URL the browser can open (file:// locally; Colab HTTPS proxy)."""
    path_p = Path(path).resolve()
    if not path_p.exists():
        raise FileNotFoundError(path_p)

    if not in_colab():
        return path_p.as_uri()

    root_p = Path(serve_root).resolve() if serve_root is not None else path_p.parent
    try:
        rel = _rel_under(path_p, root_p)
    except ValueError:
        root_p = path_p.parent
        rel = path_p.name

    port = ensure_http_root(root_p)
    from google.colab.output import eval_js

    base = eval_js(f"google.colab.kernel.proxyPort({int(port)})")
    return f"{str(base).rstrip('/')}/{rel}"


def iframe_src(path: PathLike, serve_root: Optional[PathLike] = None) -> str:
    """URL suitable for external open (legacy name kept for call sites)."""
    return browser_url(path, serve_root=serve_root)


def _links_block_html(
    entries: Sequence[tuple[str, str, str]],
    *,
    title: str,
) -> str:
    """Build a plain list of links to the HTML files (open in a new tab)."""
    bits = [
        '<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif;line-height:1.55">',
        f'<h3 style="color:#1b5e20;margin:0 0 10px">{html.escape(title)}</h3>',
        "<ul style=\"padding-left:1.2em;margin:0\">",
    ]
    for label, href, disk in entries:
        safe_href = html.escape(href, quote=True)
        full_path = html.escape(disk)
        bits.append(
            "<li style=\"margin:0 0 14px\">"
            f"<div style=\"font-weight:600\">{html.escape(label)}</div>"
            f'<div style="margin:4px 0">'
            f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer" '
            f'style="word-break:break-all;font-family:Consolas,Monaco,monospace;'
            f'font-size:13px">{full_path}</a></div>'
            f"<div style=\"font-size:11px;color:#666\">Open URL: "
            f'<a href="{safe_href}" target="_blank" rel="noopener noreferrer" '
            f'style="word-break:break-all">{html.escape(href)}</a></div>'
            "</li>"
        )
    bits.append("</ul></div>")
    return "".join(bits)


def deliverable_links_html(
    items: Sequence[LinkItem],
    *,
    serve_root: PathLike,
    title: str = "Links to HTML files",
) -> str:
    """Local Jupyter: static ``file://`` links to the HTML files."""
    root_p = Path(serve_root).resolve()
    entries = []
    for label, path in items:
        path_p = Path(path)
        if not path_p.exists() or path_p.suffix.lower() not in {".html", ".htm"}:
            continue
        href = path_p.resolve().as_uri()
        entries.append((label, href, str(path_p)))
    return _links_block_html(entries, title=title)


def display_html_deliverables(
    items: Sequence[LinkItem],
    *,
    serve_root: PathLike,
    title: str = "Links to HTML files",
    iframe_height: int = 640,  # kept for call-site compatibility; unused (tabs only)
) -> None:
    """List clickable links to the HTML files (open outside the notebook)."""
    from IPython.display import HTML, display

    del iframe_height  # tabs-only UI

    root_p = Path(serve_root).resolve()
    entries: list[tuple[str, str, str]] = []

    if in_colab():
        port = ensure_http_root(root_p)
        from google.colab.output import eval_js

        base = str(eval_js(f"google.colab.kernel.proxyPort({int(port)})")).rstrip("/")
        for label, path in items:
            path_p = Path(path)
            if not path_p.exists() or path_p.suffix.lower() not in {".html", ".htm"}:
                continue
            try:
                rel = _rel_under(path_p, root_p)
            except ValueError:
                continue
            href = f"{base}/{rel}"
            entries.append((label, href, str(path_p)))
    else:
        for label, path in items:
            path_p = Path(path)
            if not path_p.exists() or path_p.suffix.lower() not in {".html", ".htm"}:
                continue
            entries.append((label, path_p.resolve().as_uri(), str(path_p)))

    if not entries:
        display(HTML(
            f"<p><b>{html.escape(title)}</b> — no HTML files found under "
            f"<code>{html.escape(str(root_p))}</code>.</p>"
        ))
        return

    display(HTML(_links_block_html(entries, title=title)))
    print("Links to HTML files (full path → opens in a new tab):")
    for label, href, disk in entries:
        print(f"  - {label}")
        print(f"    {disk}")
        print(f"    {href}")

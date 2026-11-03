# -*- coding: utf-8 -*-
"""Open HTML deliverables in an external browser tab (never inside the .ipynb).

Colab blocks ``file://`` links from the notebook origin. Working approach:
serve files over HTTP on the kernel, then create ``target=_blank`` links in the
Colab output frame via ``google.colab.kernel.proxyPort`` so each HTML opens
outside the notebook.
"""

from __future__ import annotations

import html
import json
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
    """URL suitable for ``IPython.display.IFrame`` (local) / proxy (Colab)."""
    return browser_url(path, serve_root=serve_root)


def deliverable_links_html(
    items: Sequence[LinkItem],
    *,
    serve_root: PathLike,
    title: str = "Open national HTML deliverables",
) -> str:
    """Local Jupyter: static ``file://`` buttons. Prefer ``display_html_deliverables`` on Colab."""
    root_p = Path(serve_root).resolve()
    bits = [
        '<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif;line-height:1.5">',
        f'<h3 style="color:#1b5e20;margin:0 0 8px">{html.escape(title)}</h3>',
    ]
    for label, path in items:
        path_p = Path(path)
        if not path_p.exists() or path_p.suffix.lower() not in {".html", ".htm"}:
            continue
        href = path_p.resolve().as_uri()
        bits.append(
            f'<p style="margin:8px 0"><a style="display:inline-block;padding:10px 14px;'
            f"background:#14351c;color:#fff;text-decoration:none;border-radius:8px;"
            f'font-weight:600" href="{html.escape(href, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(label)}</a>'
            f'<br/><code style="font-size:12px">{html.escape(str(path_p))}</code></p>'
        )
    bits.append("</div>")
    return "".join(bits)


def display_html_deliverables(
    items: Sequence[LinkItem],
    *,
    serve_root: PathLike,
    title: str = "Open national HTML deliverables",
    iframe_height: int = 640,  # kept for call-site compatibility; unused (tabs only)
) -> None:
    """Show green buttons that open each HTML deliverable in a separate browser tab."""
    from IPython.display import HTML, Javascript, display

    del iframe_height  # tabs-only UI

    root_p = Path(serve_root).resolve()
    payload = []
    for label, path in items:
        path_p = Path(path)
        if not path_p.exists() or path_p.suffix.lower() not in {".html", ".htm"}:
            continue
        try:
            rel = "/" + _rel_under(path_p, root_p)
        except ValueError:
            continue
        payload.append({"label": label, "path": rel, "disk": str(path_p)})

    if not payload:
        display(HTML(f"<p><b>{html.escape(title)}</b> — no HTML files found under "
                     f"<code>{html.escape(str(root_p))}</code>.</p>"))
        return

    if not in_colab():
        display(HTML(deliverable_links_html(
            [(x["label"], x["disk"]) for x in payload],
            serve_root=root_p,
            title=title,
        )))
        return

    # Colab: resolve proxyPort inside the output frame, then target=_blank links
    # (same UX as before; file:// cannot open from Colab).
    port = ensure_http_root(root_p)
    code = """
    (async (port, items, title, element) => {
      if (!google.colab.kernel.accessAllowed) {
        element.appendChild(document.createTextNode(
          'Colab kernel access not allowed — re-run this cell while connected.'));
        return;
      }
      const base = await google.colab.kernel.proxyPort(port);
      const wrap = document.createElement('div');
      wrap.style.fontFamily = 'IBM Plex Sans, Segoe UI, sans-serif';
      wrap.style.lineHeight = '1.5';

      const heading = document.createElement('h3');
      heading.style.cssText = 'color:#1b5e20;margin:0 0 8px';
      heading.textContent = title;
      wrap.appendChild(heading);

      for (const it of items) {
        const row = document.createElement('p');
        row.style.margin = '8px 0';

        const href = new URL(it.path, base).toString();
        const openBtn = document.createElement('a');
        openBtn.href = href;
        openBtn.target = '_blank';
        openBtn.rel = 'noopener noreferrer';
        openBtn.textContent = it.label;
        openBtn.style.cssText = 'display:inline-block;padding:10px 14px;background:#14351c;color:#fff;text-decoration:none;border-radius:8px;font-weight:600';
        openBtn.addEventListener('click', (ev) => {
          // Force a real new tab even if Colab intercepts default navigation.
          ev.preventDefault();
          const w = window.open(href, '_blank', 'noopener,noreferrer');
          if (!w) {
            // Popup blocked: fall back to default anchor navigation.
            window.top.open(href, '_blank');
          }
        });

        const codeEl = document.createElement('code');
        codeEl.style.display = 'block';
        codeEl.style.fontSize = '12px';
        codeEl.style.marginTop = '4px';
        codeEl.textContent = it.disk;

        row.appendChild(openBtn);
        row.appendChild(codeEl);
        wrap.appendChild(row);
      }
      element.appendChild(wrap);
    })
    """ + f"({int(port)}, {json.dumps(payload)}, {json.dumps(title)}, window.element)"
    display(Javascript(code))

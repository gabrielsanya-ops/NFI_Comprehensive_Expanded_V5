# -*- coding: utf-8 -*-
"""Browser-openable HTML deliverables for local Jupyter and Google Colab.

Colab blocks ``file://`` links from the notebook origin. Chrome also broke
``serve_kernel_port_as_window`` (storage partitioning). Working approach:
serve files over HTTP on the kernel, then create clickable links / iframes
in the Colab output frame via ``google.colab.kernel.proxyPort``.
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
    iframe_height: int = 640,
) -> None:
    """Show clickable HTML deliverables that work in Colab and local Jupyter."""
    from IPython.display import HTML, Javascript, display

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

    port = ensure_http_root(root_p)
    display(HTML(
        f'<div style="font-family:IBM Plex Sans,Segoe UI,sans-serif">'
        f'<h3 style="color:#1b5e20;margin:0 0 8px">{html.escape(title)}</h3>'
        f'<p style="margin:0 0 10px;color:#333;font-size:13px">'
        f"Colab blocks <code>file://</code> paths. Buttons below use Colab&rsquo;s HTTP "
        f"proxy. Prefer <b>Show here</b> if a new tab is blank.</p></div>"
    ))

    # Build anchors/iframes inside the Colab output frame (required for proxyPort).
    code = """
    (async (port, items, height, element) => {
      if (!google.colab.kernel.accessAllowed) {
        element.appendChild(document.createTextNode(
          'Colab kernel access not allowed — re-run this cell while connected.'));
        return;
      }
      const base = await google.colab.kernel.proxyPort(port);
      const wrap = document.createElement('div');
      wrap.style.fontFamily = 'IBM Plex Sans, Segoe UI, sans-serif';
      wrap.style.lineHeight = '1.5';

      const viewer = document.createElement('iframe');
      viewer.width = '100%';
      viewer.height = String(height);
      viewer.style.border = '1px solid #cfd8dc';
      viewer.style.borderRadius = '8px';
      viewer.style.marginTop = '12px';
      viewer.style.display = 'none';
      viewer.allow = 'clipboard-read; clipboard-write';

      for (const it of items) {
        const row = document.createElement('p');
        row.style.margin = '8px 0';

        const openBtn = document.createElement('a');
        openBtn.href = new URL(it.path, base).toString();
        openBtn.target = '_blank';
        openBtn.rel = 'noopener noreferrer';
        openBtn.textContent = it.label;
        openBtn.style.cssText = 'display:inline-block;padding:10px 14px;background:#14351c;color:#fff;text-decoration:none;border-radius:8px;font-weight:600;margin-right:8px';

        const showBtn = document.createElement('button');
        showBtn.type = 'button';
        showBtn.textContent = 'Show here';
        showBtn.style.cssText = 'display:inline-block;padding:10px 14px;background:#eceff1;color:#14351c;border:1px solid #90a4ae;border-radius:8px;font-weight:600;cursor:pointer';
        showBtn.onclick = () => {
          viewer.style.display = 'block';
          viewer.src = new URL(it.path, base).toString();
        };

        const codeEl = document.createElement('code');
        codeEl.style.display = 'block';
        codeEl.style.fontSize = '12px';
        codeEl.style.marginTop = '4px';
        codeEl.textContent = it.disk;

        row.appendChild(openBtn);
        row.appendChild(showBtn);
        row.appendChild(codeEl);
        wrap.appendChild(row);
      }
      wrap.appendChild(viewer);
      element.appendChild(wrap);

      // Auto-show the first deliverable in-notebook (most reliable on Colab).
      if (items.length) {
        viewer.style.display = 'block';
        viewer.src = new URL(items[0].path, base).toString();
      }
    })
    """ + f"({int(port)}, {json.dumps(payload)}, {int(iframe_height)}, window.element)"
    display(Javascript(code))

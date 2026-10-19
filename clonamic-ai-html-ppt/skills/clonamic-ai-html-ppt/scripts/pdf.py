"""Headless Chrome jobs on print.html: PDF export, PNG snapshots, text measurement; plus stdlib PDF/PNG readers."""

from __future__ import annotations

import base64
import json
import os
import re
import select
import shutil
import signal
import struct
import tempfile
import time
import zlib
from pathlib import Path
from typing import Callable

TIMEOUT = 120
MAC_APPS = ("Google Chrome", "Chromium", "Microsoft Edge", "Google Chrome Canary")
LINUX_BINS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge")


class ChromeMissing(Exception):
    """No Chrome/Chromium/Edge here → HTTP 503 with fallback "print"."""


class PdfError(Exception):
    """Chrome ran but produced nothing usable."""


def find_chrome() -> str | None:
    env = os.environ.get("PPT_CHROME")
    if env:
        return env if os.access(env, os.X_OK) else None
    for app in MAC_APPS:
        path = f"/Applications/{app}.app/Contents/MacOS/{app}"
        if os.access(path, os.X_OK):
            return path
    return next((p for p in map(shutil.which, LINUX_BINS) if p), None)


# The mock keychain and basic password store keep macOS from showing a "keychain not found" dialog.
BASE_ARGS = ("--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--use-mock-keychain",
             "--password-store=basic", "--disable-features=MediaRouter", "--disable-sync", "--hide-scrollbars")
READY = "window.__PPT_READY__ === true"


def command(chrome: str, url: str, profile: str, *extra: str) -> list[str]:
    return [chrome, *BASE_ARGS, f"--user-data-dir={profile}", *extra, url]


def need_chrome() -> str:
    chrome = find_chrome()
    if chrome is None:
        raise ChromeMissing("Chrome, Chromium, Edge를 찾지 못했습니다. 브라우저의 인쇄(PDF로 저장)를 쓰세요.")
    return chrome


class Chrome:
    """Headless Chrome driven over --remote-debugging-pipe (CDP on fds 3/4: no debug port), with a fresh profile.

    print.html renders asynchronously, so every job waits for window.__PPT_READY__ before it prints, captures, or reads.
    """

    def __init__(self, chrome: str, timeout: float = TIMEOUT):
        self.deadline = time.monotonic() + timeout
        self.profile = tempfile.mkdtemp(prefix="ppt-chrome-")
        to_chrome, from_chrome = os.pipe(), os.pipe()
        null = os.open(os.devnull, os.O_RDWR)
        dup = os.POSIX_SPAWN_DUP2
        try:  # posix_spawn: no fork of this threaded server, and fd 3/4 land exactly where Chrome expects them
            self.pid = os.posix_spawn(chrome, command(chrome, "about:blank", self.profile, "--remote-debugging-pipe"), os.environ,
                                      file_actions=[(dup, null, 0), (dup, null, 1), (dup, null, 2),
                                                    (dup, to_chrome[0], 3), (dup, from_chrome[1], 4)], setpgroup=0)
        except OSError:
            shutil.rmtree(self.profile, ignore_errors=True)
            raise
        finally:
            for fd in (null, to_chrome[0], from_chrome[1]):
                os.close(fd)
        self.out, self.inp, self.buf, self.n = to_chrome[1], from_chrome[0], b"", 0

    def __enter__(self) -> "Chrome":
        return self

    def __exit__(self, *exc) -> None:
        for fd in (self.out, self.inp):
            os.close(fd)
        try:
            os.killpg(self.pid, signal.SIGKILL)  # Chrome and every helper it started
        except (ProcessLookupError, PermissionError):
            pass
        os.waitpid(self.pid, 0)
        shutil.rmtree(self.profile, ignore_errors=True)

    def _message(self) -> dict:
        while b"\0" not in self.buf:
            left = self.deadline - time.monotonic()
            if left <= 0 or not select.select([self.inp], [], [], left)[0]:
                raise PdfError(f"Chrome이 {TIMEOUT}초 안에 끝나지 않았습니다.")
            chunk = os.read(self.inp, 1 << 20)
            if not chunk:
                raise PdfError("Chrome이 중간에 종료됐습니다.")
            self.buf += chunk
        raw, self.buf = self.buf.split(b"\0", 1)
        return json.loads(raw)

    def send(self, method: str, params: dict | None = None, session: str | None = None) -> dict:
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}} | ({"sessionId": session} if session else {})
        data = json.dumps(msg).encode() + b"\0"
        while data:
            data = data[os.write(self.out, data):]
        while True:
            reply = self._message()
            if reply.get("id") == self.n:  # events (no id) are not used
                if "error" in reply:
                    raise PdfError(f"{method}: {reply['error'].get('message')}")
                return reply["result"]

    def open(self, url: str, width: int | None = None, height: int | None = None) -> str:
        """A new tab at `url` (viewport width×height CSS px), returned once the page says it is ready."""
        target = self.send("Target.createTarget", {"url": "about:blank"})["targetId"]
        session = self.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        if width:
            self.send("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1,
                                                             "mobile": False}, session)
        self.send("Page.navigate", {"url": url}, session)
        while True:
            try:
                if self.evaluate(READY, session):
                    return session
            except PdfError as exc:
                if "context" not in str(exc).lower():  # the old document went away mid-call: just ask again
                    raise
            if time.monotonic() > self.deadline:
                raise PdfError("인쇄 화면이 준비되지 않았습니다(__PPT_READY__).")
            time.sleep(0.05)

    def evaluate(self, expression: str, session: str):
        result = self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True}, session)
        if "exceptionDetails" in result:
            raise PdfError("페이지 스크립트 오류: " + str(result["exceptionDetails"].get("text")))
        return result["result"].get("value")


def render(chrome: str, url: str, out: Path, timeout: float = TIMEOUT) -> None:
    """PDF with each page at its CSS @page size."""
    with Chrome(chrome, timeout) as c:
        page = c.open(url)
        data = c.send("Page.printToPDF", {"printBackground": True, "preferCSSPageSize": True, "displayHeaderFooter": False,
                                          "marginTop": 0, "marginBottom": 0, "marginLeft": 0, "marginRight": 0}, page)["data"]
    out.write_bytes(base64.b64decode(data))


def screenshot(url: str, out: Path, w: int, h: int) -> None:
    """PNG of the page in a w×h CSS px viewport (print.html snapshot mode sizes its body to match)."""
    with Chrome(need_chrome()) as c:
        page = c.open(url, w, h)
        data = c.send("Page.captureScreenshot", {"format": "png"}, page)["data"]
    out.write_bytes(base64.b64decode(data))


def measure(url: str) -> dict:
    """The {id: {x, y, w, h, sw, sh}} JSON print.html's measure mode appends as <script id="ppt-measure">."""
    with Chrome(need_chrome()) as c:
        text = c.evaluate('document.getElementById("ppt-measure")?.textContent ?? null', c.open(url))
    if text is None:
        raise PdfError("측정 결과(ppt-measure)가 페이지에 없습니다.")
    return json.loads(text)


def png_size(path: str | Path) -> tuple[int, int]:
    head = Path(path).read_bytes()[:24]
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG가 아닙니다.")
    return struct.unpack(">II", head[16:24])


def safe_name(name: str, fallback: str = "deck") -> str:
    name = re.sub(r'[\x00-\x1f/\\:*?"<>|]+', "_", name).strip(" .")
    return name[:100] or fallback


def unique(path: Path) -> Path:
    """`name.pdf`, else `name (2).pdf`, `name (3).pdf`, … — never overwrite."""
    n, candidate = 2, path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        n += 1
    return candidate


def export(url_for: Callable[[list[str]], str], deck_name: str, pages: list[tuple[int, str, str]], mode: str,
           folder: str = "~/Downloads") -> list[str]:
    """pages = [(1-based index, id, name)]. single: one PDF in order; each: one PDF per page. Returns absolute paths."""
    chrome = need_chrome()
    target = Path(folder).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    deck = safe_name(deck_name)
    if mode == "single":
        jobs = [([pid for _, pid, _ in pages], f"{deck}.pdf")]
    else:
        jobs = [([pid], f"{deck}-{i}-{safe_name(name, 'page')}.pdf") for i, pid, name in pages]
    files = []
    for ids, filename in jobs:
        out = unique(target / filename)
        render(chrome, url_for(ids), out)
        files.append(str(out))
    return files


# ---- MediaBox reader ------------------------------------------------------------------------------

OBJ = re.compile(rb"(\d+)\s+\d+\s+obj\b(.*?)\bendobj", re.S)


def _stream(body: bytes) -> bytes:
    start = body.index(b"stream") + 6
    start += 2 if body[start:start + 2] == b"\r\n" else 1
    raw = body[start:body.rindex(b"endstream")]
    return zlib.decompress(raw) if b"/FlateDecode" in body[:start] else raw


def _objects(data: bytes) -> dict[int, bytes]:
    """Object number → body, including objects packed in compressed object streams."""
    objs = {int(m[1]): m[2] for m in OBJ.finditer(data)}
    for body in list(objs.values()):
        head = body.split(b"stream", 1)[0]
        if re.search(rb"/Type\s*/ObjStm", head):
            raw = _stream(body)
            first = int(re.search(rb"/First\s+(\d+)", head)[1])
            nums = [int(x) for x in raw[:first].split()]
            pairs = list(zip(nums[::2], nums[1::2]))
            for k, (num, off) in enumerate(pairs):
                end = pairs[k + 1][1] if k + 1 < len(pairs) else len(raw) - first
                objs.setdefault(num, raw[first + off:first + end])
    return objs


def mediaboxes(path: str | Path) -> list[tuple[float, float]]:
    """(w, h) in pt of every page, in page-tree order (MediaBox inherited from /Pages nodes)."""
    objs = _objects(Path(path).read_bytes())
    catalog = next(b for b in objs.values() if re.search(rb"/Type\s*/Catalog\b", b))
    out: list[tuple[float, float]] = []

    def walk(num: int, inherited: list[float] | None) -> None:
        body = objs[num].split(b"stream", 1)[0]
        m = re.search(rb"/MediaBox\s*\[([^\]]*)\]", body)
        box = [float(x) for x in m[1].split()] if m else inherited
        if re.search(rb"/Type\s*/Pages\b", body):
            for kid in re.findall(rb"(\d+)\s+\d+\s+R", re.search(rb"/Kids\s*\[([^\]]*)\]", body)[1]):
                walk(int(kid), box)
        elif box:
            out.append((round(box[2] - box[0], 2), round(box[3] - box[1], 2)))

    walk(int(re.search(rb"/Pages\s+(\d+)\s+\d+\s+R", catalog)[1]), None)
    return out

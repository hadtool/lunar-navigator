"""Static copy of the animated deck: seven PNGs and docs/demo/slides.pdf (task T27).

    uv run python pipeline/export_deck.py

Opens docs/demo/deck/index.html?static=1 (every slide in its final state, no animation) in a
headless Firefox, takes one 1920 x 1080 screenshot per slide and joins them into a PDF of seven
pages. Needs only Firefox on the PATH and Pillow; the browser is driven over the Marionette
socket, so no driver has to be installed. Stops if a slide reports a script error.
"""

from __future__ import annotations

import base64
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DECK = ROOT / "docs" / "demo" / "deck" / "index.html"
OUT_DIR = ROOT / "docs" / "demo" / "slides"
PDF = ROOT / "docs" / "demo" / "slides.pdf"
SLIDES = 7
WIDTH, HEIGHT = 1920, 1080
PORT = 2837


class Browser:
    """Minimal Marionette client for a headless Firefox started by this process."""

    def __init__(self, port: int = PORT) -> None:
        self._profile = tempfile.TemporaryDirectory(prefix="deck-firefox-")
        Path(self._profile.name, "user.js").write_text(
            f'user_pref("marionette.port", {port});\nuser_pref("browser.shell.checkDefaultBrowser", false);\n'
            'user_pref("datareporting.policy.dataSubmissionEnabled", false);\n', encoding="utf-8")
        self._process = subprocess.Popen(
            ["firefox", "--headless", "--marionette", "--no-remote", "--profile", self._profile.name,
             "--width", str(WIDTH), "--height", str(HEIGHT)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 60
        while True:
            try:
                self._socket = socket.create_connection(("127.0.0.1", port), timeout=120)
                break
            except OSError:
                if time.monotonic() > deadline:
                    self.close()
                    raise RuntimeError("Firefox did not open the Marionette port") from None
                time.sleep(0.5)
        self._file = self._socket.makefile("rb")
        self._id = 0
        self._read()
        self.command("WebDriver:NewSession", {"capabilities": {}})

    def _read(self) -> list:
        length = b""
        while (char := self._file.read(1)) != b":":
            if not char:
                raise RuntimeError("Firefox closed the connection")
            length += char
        return json.loads(self._file.read(int(length)))

    def command(self, name: str, parameters: dict | None = None):
        self._id += 1
        message = json.dumps([0, self._id, name, parameters or {}]).encode()
        self._socket.sendall(str(len(message)).encode() + b":" + message)
        reply = self._read()
        if reply[2]:
            raise RuntimeError(f"{name}: {reply[2]}")
        return reply[3]

    def script(self, source: str, *arguments):
        return self.command("WebDriver:ExecuteScript", {"script": source, "args": list(arguments)})["value"]

    def viewport(self, width: int, height: int) -> None:
        """Resize the window until the page area itself is width x height."""
        self.command("WebDriver:SetWindowRect", {"width": width, "height": height})
        inner = self.script("return [window.innerWidth, window.innerHeight]")
        self.command("WebDriver:SetWindowRect", {"width": 2 * width - inner[0], "height": 2 * height - inner[1]})

    def open(self, url: str, ready: str = "return document.readyState === 'complete'", timeout: float = 30) -> None:
        self.command("WebDriver:Navigate", {"url": url})
        deadline = time.monotonic() + timeout
        while not self.script(ready):
            if time.monotonic() > deadline:
                raise RuntimeError(f"page not ready: {url}")
            time.sleep(0.2)

    def screenshot(self, path: Path) -> None:
        data = self.command("WebDriver:TakeScreenshot", {"full": False})["value"]
        path.write_bytes(base64.b64decode(data))

    def close(self) -> None:
        try:
            self.command("Marionette:Quit", {"flags": ["eForceQuit"]})
        except Exception:  # noqa: BLE001 - the browser may already be gone
            pass
        try:
            self._process.wait(timeout=10)
        except Exception:  # noqa: BLE001
            self._process.kill()
        self._profile.cleanup()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    browser = Browser()
    pages = []
    try:
        browser.viewport(WIDTH, HEIGHT)
        for number in range(1, SLIDES + 1):
            # a fresh page per slide: the query string differs, so the browser reloads it
            browser.open(f"{DECK.as_uri()}?static=1&n={number}#{number}", "return !!(window.__ready && window.__ready())")
            time.sleep(1.0)
            errors = browser.script("return window.__errors")
            if errors:
                raise SystemExit(f"slide {number}: script errors {errors}")
            path = OUT_DIR / f"slide_{number}.png"
            browser.screenshot(path)
            image = Image.open(path).convert("RGB")
            if image.size != (WIDTH, HEIGHT):
                raise SystemExit(f"slide {number}: screenshot is {image.size}, expected {(WIDTH, HEIGHT)}")
            image.save(path, optimize=True)
            pages.append(image)
    finally:
        browser.close()
    pages[0].save(
        PDF, save_all=True, append_images=pages[1:], resolution=144.0,
        title="Lunar Landing Site Navigator - demo slides", author="Team COSMOSMARTES",
        subject="NASA Space Apps Challenge 2026. AI-generated deck: visuals and layout made with Claude (Anthropic); "
                "numbers computed from NASA data by the project's code.",
        creator="pipeline/export_deck.py")
    print(f"wrote {PDF.relative_to(ROOT)} ({PDF.stat().st_size / 1024:.0f} KB) and {len(pages)} PNGs in "
          f"{OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

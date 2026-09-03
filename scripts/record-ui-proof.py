from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import struct
import subprocess
import time
import urllib.request
import wave
from pathlib import Path

from PIL import Image


CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
FRONTEND_URL = os.environ.get("PRODUCT_TO_MCP_FRONTEND_URL", "http://127.0.0.1:5175")
OPENAPI_FILE = Path("examples/demo-openapi.yaml").resolve()
OUTPUT_DIR = Path(".runtime/evidence").resolve()
REMOTE_DEBUGGING_PORT = int(os.environ.get("PRODUCT_TO_MCP_CHROME_DEBUG_PORT", "9224"))
FFMPEG_PATH = os.environ.get("PRODUCT_TO_MCP_FFMPEG_PATH")


class CdpClient:
    def __init__(self, websocket_url: str) -> None:
        self.sock = self._connect(websocket_url)
        self.next_id = 1

    def call(self, method: str, params: dict | None = None) -> dict:
        request_id = self.next_id
        self.next_id += 1
        self._send_json({"id": request_id, "method": method, "params": params or {}})
        while True:
            message = self._recv_json()
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def close(self) -> None:
        self.sock.close()

    @staticmethod
    def _connect(websocket_url: str) -> socket.socket:
        if not websocket_url.startswith("ws://"):
            raise ValueError("Only ws:// CDP URLs are supported.")
        without_scheme = websocket_url[len("ws://"):]
        host_port, path = without_scheme.split("/", 1)
        host, port = host_port.split(":", 1)
        sock = socket.create_connection((host, int(port)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode())
        response = sock.recv(4096)
        if b" 101 " not in response:
            raise RuntimeError(response.decode(errors="replace"))
        return sock

    def _send_json(self, message: dict) -> None:
        payload = json.dumps(message).encode()
        header = bytearray([0x81])
        if len(payload) < 126:
            header.append(0x80 | len(payload))
        elif len(payload) < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", len(payload)))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", len(payload)))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.sendall(header + masked)

    def _recv_json(self) -> dict:
        while True:
            first, second = self._read_exact(2)
            opcode = first & 0x0F
            masked = second & 0x80
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack("!Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if masked else b""
            payload = self._read_exact(length)
            if masked:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 8:
                raise RuntimeError("CDP websocket closed.")
            if opcode == 1:
                return json.loads(payload.decode())

    def _read_exact(self, length: int) -> bytes:
        data = bytearray()
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                raise RuntimeError("Socket closed.")
            data.extend(chunk)
        return bytes(data)


def chrome_targets() -> list[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{REMOTE_DEBUGGING_PORT}/json/list", timeout=5) as response:
        return json.loads(response.read())


def wait_for_chrome() -> str:
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            targets = chrome_targets()
            for target in targets:
                if target.get("type") == "page":
                    return target["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("Chrome DevTools target did not become ready.")


def evaluate(cdp: CdpClient, expression: str) -> object:
    result = cdp.call("Runtime.evaluate", {"expression": expression, "awaitPromise": True, "returnByValue": True})
    if result.get("exceptionDetails"):
        raise RuntimeError(result["exceptionDetails"])
    return result.get("result", {}).get("value")


def wait_for(cdp: CdpClient, expression: str, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if evaluate(cdp, expression):
            return
        time.sleep(0.25)
    raise TimeoutError(expression)


def screenshot(cdp: CdpClient, name: str, frames: list[Path]) -> None:
    path = OUTPUT_DIR / name
    data = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
    path.write_bytes(base64.b64decode(data))
    frames.append(path)


def set_file_input(cdp: CdpClient) -> None:
    root = cdp.call("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]
    node = cdp.call("DOM.querySelector", {"nodeId": root, "selector": "input[type=file]"})["nodeId"]
    cdp.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(OPENAPI_FILE)]})


def make_gif(frames: list[Path]) -> Path:
    images = [Image.open(frame).convert("P", palette=Image.Palette.ADAPTIVE) for frame in frames]
    output = OUTPUT_DIR / "product-to-mcp-crud-ui-proof.gif"
    images[0].save(output, save_all=True, append_images=images[1:], duration=1500, loop=0)
    return output


def find_ffmpeg() -> Path | None:
    candidates = []
    if FFMPEG_PATH:
        candidates.append(Path(FFMPEG_PATH))
    candidates.extend(
        [
            Path(r"C:\Users\Priyanshu\Downloads\ffmpeg-9.0.1\bin\ffmpeg.exe"),
            Path(r"C:\Users\Priyanshu\Downloads\ffmpeg-9.0.1\ffmpeg-9.0.1\bin\ffmpeg.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def make_silent_audio(path: Path, duration_seconds: int) -> None:
    sample_rate = 44_100
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(b"\x00\x00" * sample_rate * duration_seconds)


def make_mp4_with_ffmpeg(frames: list[Path]) -> Path | None:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return None
    concat_file = OUTPUT_DIR / "ui-proof-frames.ffconcat"
    audio_file = OUTPUT_DIR / "ui-proof-silent.wav"
    output = OUTPUT_DIR / "product-to-mcp-crud-ui-proof.mp4"
    lines = ["ffconcat version 1.0"]
    for frame in frames:
        lines.append(f"file '{frame.as_posix()}'")
        lines.append("duration 1.5")
    lines.append(f"file '{frames[-1].as_posix()}'")
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    make_silent_audio(audio_file, max(1, int(len(frames) * 1.5) + 1))
    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-i",
            str(audio_file),
            "-shortest",
            "-vf",
            "fps=30,format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-movflags",
            "+faststart",
            str(output),
        ],
        check=True,
    )
    return output


def make_mjpeg_avi(frames: list[Path]) -> Path:
    output = OUTPUT_DIR / "product-to-mcp-crud-ui-proof.avi"
    image = Image.open(frames[0]).convert("RGB")
    width, height = image.size
    fps = 1
    repeated_frames = []
    for frame in frames:
        repeated_frames.extend([frame, frame])
    frame_count = len(repeated_frames)

    def chunk(chunk_id: bytes, data: bytes) -> bytes:
        padding = b"\x00" if len(data) % 2 else b""
        return chunk_id + len(data).to_bytes(4, "little") + data + padding

    jpeg_frames = []
    for frame in repeated_frames:
        current = Image.open(frame).convert("RGB")
        if current.size != (width, height):
            current = current.resize((width, height))
        from io import BytesIO

        buffer = BytesIO()
        current.save(buffer, format="JPEG", quality=85)
        jpeg_frames.append(buffer.getvalue())

    movi_data = b"".join(chunk(b"00dc", frame) for frame in jpeg_frames)
    hdrl = (
        b"avih"
        + (56).to_bytes(4, "little")
        + (1_000_000 // fps).to_bytes(4, "little")
        + (width * height * 3 * fps).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (0x10).to_bytes(4, "little")
        + frame_count.to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (1).to_bytes(4, "little")
        + (width * height * 3).to_bytes(4, "little")
        + width.to_bytes(4, "little")
        + height.to_bytes(4, "little")
        + (0).to_bytes(16, "little")
    )
    strh = (
        b"strh"
        + (56).to_bytes(4, "little")
        + b"vids"
        + b"MJPG"
        + (0).to_bytes(4, "little")
        + (0).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + (0).to_bytes(4, "little")
        + (1).to_bytes(4, "little")
        + fps.to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + frame_count.to_bytes(4, "little")
        + (width * height * 3).to_bytes(4, "little")
        + (0xFFFFFFFF).to_bytes(4, "little")
        + (0).to_bytes(4, "little")
        + (0).to_bytes(2, "little")
        + (0).to_bytes(2, "little")
        + width.to_bytes(2, "little")
        + height.to_bytes(2, "little")
    )
    strf = (
        b"strf"
        + (40).to_bytes(4, "little")
        + (40).to_bytes(4, "little")
        + width.to_bytes(4, "little")
        + height.to_bytes(4, "little")
        + (1).to_bytes(2, "little")
        + (24).to_bytes(2, "little")
        + b"MJPG"
        + (width * height * 3).to_bytes(4, "little")
        + (0).to_bytes(16, "little")
    )
    strl = b"LIST" + (4 + len(strh) + len(strf)).to_bytes(4, "little") + b"strl" + strh + strf
    hdrl_list = b"LIST" + (4 + len(hdrl) + len(strl)).to_bytes(4, "little") + b"hdrl" + hdrl + strl
    movi_list = b"LIST" + (4 + len(movi_data)).to_bytes(4, "little") + b"movi" + movi_data
    avi = b"RIFF" + (4 + len(hdrl_list) + len(movi_list)).to_bytes(4, "little") + b"AVI " + hdrl_list + movi_list
    output.write_bytes(avi)
    return output


def main() -> None:
    if not CHROME.exists():
        raise RuntimeError(f"Chrome not found at {CHROME}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    user_data_dir = OUTPUT_DIR / "chrome-profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        [
            str(CHROME),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={REMOTE_DEBUGGING_PORT}",
            f"--user-data-dir={user_data_dir}",
            "--window-size=1366,900",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    frames: list[Path] = []
    try:
        cdp = CdpClient(wait_for_chrome())
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("DOM.enable")
        cdp.call("Page.navigate", {"url": FRONTEND_URL})
        wait_for(cdp, "Boolean(document.querySelector('h1'))")
        screenshot(cdp, "01-home.png", frames)

        evaluate(
            cdp,
            """
            (() => {
              const setValue = (element, value) => {
                const setter = Object.getOwnPropertyDescriptor(element.constructor.prototype, 'value').set;
                setter.call(element, value);
                element.dispatchEvent(new Event('input', { bubbles: true }));
              };
              const inputs = [...document.querySelectorAll('input')];
              setValue(inputs[0], 'Recorded CRUD Demo');
              setValue(inputs[1], 'http://127.0.0.1:9001');
              document.querySelector('button').click();
              return true;
            })()
            """,
        )
        wait_for(cdp, "document.body.innerText.includes('Upload an OpenAPI document')")
        screenshot(cdp, "02-project-created.png", frames)

        set_file_input(cdp)
        wait_for(cdp, "document.body.innerText.includes('createproduct') && !document.body.innerText.includes('Prototype supports GET/HEAD')")
        screenshot(cdp, "03-crud-tools-enabled.png", frames)

        evaluate(cdp, "[...document.querySelectorAll('button')].find(button => button.textContent.includes('Generate MCP release')).click(); true")
        wait_for(cdp, "document.body.innerText.includes('MCP release created')")
        screenshot(cdp, "04-release-created.png", frames)

        evaluate(
            cdp,
            """
            (() => {
              const card = [...document.querySelectorAll('.tool-test')].find(item => item.innerText.includes('createproduct'));
              card.scrollIntoView();
              card.querySelector('button').click();
              return true;
            })()
            """,
        )
        wait_for(cdp, "document.body.innerText.includes('status_code') && document.body.innerText.includes('201')")
        screenshot(cdp, "05-create-product-success.png", frames)

        evaluate(
            cdp,
            """
            (() => {
              const setValue = (element, value) => {
                const setter = Object.getOwnPropertyDescriptor(element.constructor.prototype, 'value').set;
                setter.call(element, value);
                element.dispatchEvent(new Event('input', { bubbles: true }));
              };
              const card = [...document.querySelectorAll('.tool-test')].find(item => item.innerText.includes('listproducts'));
              setValue(card.querySelector('textarea'), JSON.stringify({ limit: 20 }, null, 2));
              card.scrollIntoView();
              card.querySelector('button').click();
              return true;
            })()
            """,
        )
        wait_for(cdp, "document.body.innerText.includes('Growth plan') || document.body.innerText.includes('p-2')")
        screenshot(cdp, "06-list-after-create.png", frames)
        cdp.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    gif = make_gif(frames)
    mp4 = make_mp4_with_ffmpeg(frames)
    avi = make_mjpeg_avi(frames)
    manifest = {
        "frontend_url": FRONTEND_URL,
        "openapi_file": str(OPENAPI_FILE),
        "frames": [str(frame) for frame in frames],
        "animated_proof": str(gif),
        "mp4_proof": str(mp4) if mp4 else None,
        "fallback_avi_proof": str(avi),
        "ffmpeg_path": str(find_ffmpeg()) if find_ffmpeg() else None,
        "gif_sha256": hashlib.sha256(gif.read_bytes()).hexdigest(),
        "mp4_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest() if mp4 else None,
        "avi_sha256": hashlib.sha256(avi.read_bytes()).hexdigest(),
    }
    manifest_path = OUTPUT_DIR / "ui-proof-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import time
import textwrap
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


MODULE_PATH = Path(__file__).with_name("record-ui-proof.py")
spec = importlib.util.spec_from_file_location("record_ui_proof", MODULE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("Could not load record-ui-proof.py")
record_ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(record_ui)

OUTPUT_DIR = Path(".runtime/evidence").resolve()
OPENAPI_FILE = Path("examples/demo-openapi.yaml").resolve()
FRONTEND_URL = "http://127.0.0.1:5175"
PRODUCT_ID = f"p-video-{int(time.time())}"


def wait_for(cdp, expression: str, timeout: float = 15) -> None:
    record_ui.wait_for(cdp, expression, timeout)


def evaluate(cdp, expression: str):
    return record_ui.evaluate(cdp, expression)


def page_png(cdp) -> Image.Image:
    data = cdp.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": True})["data"]
    return Image.open(BytesIO(base64.b64decode(data))).convert("RGB")


def browser_view(cdp) -> Image.Image:
    data = cdp.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})["data"]
    return Image.open(BytesIO(base64.b64decode(data))).convert("RGB")


def save_frame(image: Image.Image, filename: str, title: str, subtitle: str = "") -> Path:
    path = OUTPUT_DIR / filename
    canvas = Image.new("RGB", (1280, 720), "#eef2f7")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    title_font = font
    subtitle_font = font
    draw.rounded_rectangle((24, 18, 1256, 702), radius=12, fill="white", outline="#d9e0eb", width=2)
    draw.text((48, 38), title, fill="#18202b", font=title_font)
    if subtitle:
        draw.text((48, 60), subtitle, fill="#536174", font=subtitle_font)
    max_w, max_h = 1184, 590
    image.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = 48 + (max_w - image.width) // 2
    y = 94 + (max_h - image.height) // 2
    canvas.paste(image, (x, y))
    canvas.save(path, quality=92)
    return path


def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = [
        Path(r"C:\Windows\Fonts\consola.ttf") if mono else Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for path in paths:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def save_response_frame(filename: str, title: str, request: dict, response_text: str) -> Path:
    path = OUTPUT_DIR / filename
    canvas = Image.new("RGB", (1280, 720), "#eef2f7")
    draw = ImageDraw.Draw(canvas)
    title_font = font(28)
    small_font = font(17)
    code_font = font(19, mono=True)

    draw.rounded_rectangle((24, 18, 1256, 702), radius=12, fill="white", outline="#d9e0eb", width=2)
    draw.text((48, 38), title, fill="#18202b", font=title_font)
    draw.text((48, 78), "Left: MCP tool arguments sent from the UI. Right: response shown by the UI.", fill="#536174", font=small_font)

    left = (48, 120, 610, 670)
    right = (670, 120, 1232, 670)
    draw.rounded_rectangle(left, radius=8, fill="#f7f9fc", outline="#dbe2ee")
    draw.rounded_rectangle(right, radius=8, fill="#f7f9fc", outline="#dbe2ee")
    draw.text((left[0] + 18, left[1] + 14), "Request arguments", fill="#18202b", font=small_font)
    draw.text((right[0] + 18, right[1] + 14), "Tool response", fill="#18202b", font=small_font)

    request_text = json.dumps(request, indent=2)
    write_wrapped(draw, request_text, (left[0] + 18, left[1] + 48), code_font, max_chars=44, max_lines=22)
    write_wrapped(draw, response_text, (right[0] + 18, right[1] + 48), code_font, max_chars=46, max_lines=22)
    canvas.save(path, quality=92)
    return path


def write_wrapped(draw: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], draw_font, max_chars: int, max_lines: int) -> None:
    lines: list[str] = []
    for line in text.splitlines():
        if len(line) <= max_chars:
            lines.append(line)
        else:
            lines.extend(textwrap.wrap(line, width=max_chars, replace_whitespace=False, drop_whitespace=False))
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["..."]
    draw.multiline_text(xy, "\n".join(lines), fill="#172033", font=draw_font, spacing=5)


def response_text(cdp) -> str:
    value = evaluate(cdp, "document.querySelector('pre')?.innerText || ''")
    return str(value)


def tool_response_text(cdp, tool_name: str) -> str:
    tool = json.dumps(tool_name)
    value = evaluate(
        cdp,
        f"""
        (() => {{
          const card = [...document.querySelectorAll('.tool-test')].find(item => item.innerText.includes({tool}));
          return card?.querySelector('pre')?.innerText || '';
        }})()
        """,
    )
    return str(value)


def wait_for_tool_response(cdp, tool_name: str, expected: str, timeout: float = 15) -> None:
    tool = json.dumps(tool_name)
    text = json.dumps(expected)
    wait_for(
        cdp,
        f"""
        (() => {{
          const card = [...document.querySelectorAll('.tool-test')].find(item => item.innerText.includes({tool}));
          return Boolean(card?.querySelector('pre')?.innerText.includes({text}));
        }})()
        """,
        timeout,
    )


def set_file_input(cdp) -> None:
    root = cdp.call("DOM.getDocument", {"depth": -1, "pierce": True})["root"]["nodeId"]
    node = cdp.call("DOM.querySelector", {"nodeId": root, "selector": "input[type=file]"})["nodeId"]
    cdp.call("DOM.setFileInputFiles", {"nodeId": node, "files": [str(OPENAPI_FILE)]})


def set_tool_args_and_call(cdp, tool_name: str, args: dict) -> None:
    expression = json.dumps(
        {
            "tool": tool_name,
            "args": json.dumps(args, indent=2),
        }
    )
    evaluate(
        cdp,
        f"""
        (() => {{
          const payload = {expression};
          const setValue = (element, value) => {{
            const setter = Object.getOwnPropertyDescriptor(element.constructor.prototype, 'value').set;
            setter.call(element, value);
            element.dispatchEvent(new Event('input', {{ bubbles: true }}));
          }};
          const card = [...document.querySelectorAll('.tool-test')].find(item => item.innerText.includes(payload.tool));
          card.scrollIntoView();
          setValue(card.querySelector('textarea'), payload.args);
          card.querySelector('button').click();
          return true;
        }})()
        """,
    )


def save_video(frames: list[Path]) -> tuple[Path | None, Path]:
    mp4 = record_ui.make_mp4_with_ffmpeg(frames)
    avi = make_readable_avi(frames)
    return mp4, avi


def make_readable_avi(frames: list[Path]) -> Path:
    output = OUTPUT_DIR / "product-to-mcp-crud-detailed-proof.avi"
    original_output = record_ui.make_mjpeg_avi(frames)
    output.write_bytes(original_output.read_bytes())
    return output


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    process = record_ui.subprocess.Popen(
        [
            str(record_ui.CHROME),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--remote-debugging-port={record_ui.REMOTE_DEBUGGING_PORT}",
            f"--user-data-dir={OUTPUT_DIR / 'chrome-detailed-profile'}",
            "--window-size=1366,900",
            "about:blank",
        ],
        stdout=record_ui.subprocess.DEVNULL,
        stderr=record_ui.subprocess.DEVNULL,
    )
    frames: list[Path] = []
    try:
        cdp = record_ui.CdpClient(record_ui.wait_for_chrome())
        cdp.call("Page.enable")
        cdp.call("Runtime.enable")
        cdp.call("DOM.enable")
        cdp.call("Page.navigate", {"url": FRONTEND_URL})
        wait_for(cdp, "Boolean(document.querySelector('h1'))")
        frames.append(save_frame(browser_view(cdp), "detail-01-home.png", "Step 1 - Frontend loaded"))

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
              setValue(inputs[0], 'Detailed CRUD Video Demo');
              setValue(inputs[1], 'http://127.0.0.1:9001');
              [...document.querySelectorAll('button')].find(button => button.textContent.includes('Create project')).click();
              return true;
            })()
            """,
        )
        wait_for(cdp, "document.body.innerText.includes('Upload the OpenAPI document')")
        frames.append(save_frame(browser_view(cdp), "detail-02-project.png", "Step 2 - Project created", "Base URL points to the demo API on port 9001."))

        set_file_input(cdp)
        wait_for(cdp, "document.body.innerText.includes('deleteproduct') && !document.body.innerText.includes('Prototype supports GET/HEAD')")
        frames.append(save_frame(browser_view(cdp), "detail-03-tools.png", "Step 3 - OpenAPI imported", "All CRUD tools are enabled and selectable."))

        evaluate(cdp, "[...document.querySelectorAll('button')].find(button => button.textContent.includes('Generate MCP release')).click(); true")
        wait_for(cdp, "document.body.innerText.includes('MCP release created')")
        frames.append(save_frame(browser_view(cdp), "detail-04-release.png", "Step 4 - MCP release generated", "Endpoint and manifest are created."))

        create_args = {"body": {"id": PRODUCT_ID, "name": "Detailed video plan", "price": 101}}
        set_tool_args_and_call(cdp, "createproduct", create_args)
        wait_for_tool_response(cdp, "createproduct", "201")
        frames.append(save_response_frame("detail-05-create-response.png", "Step 5 - createproduct: POST returns 201", create_args, tool_response_text(cdp, "createproduct")))

        get_args = {"product_id": PRODUCT_ID}
        set_tool_args_and_call(cdp, "getproduct", get_args)
        wait_for_tool_response(cdp, "getproduct", "Detailed video plan")
        frames.append(save_response_frame("detail-06-get-response.png", "Step 6 - getproduct: GET returns created product", get_args, tool_response_text(cdp, "getproduct")))

        replace_args = {"product_id": PRODUCT_ID, "body": {"id": PRODUCT_ID, "name": "Replaced video plan", "price": 121}}
        set_tool_args_and_call(cdp, "replaceproduct", replace_args)
        wait_for_tool_response(cdp, "replaceproduct", "Replaced video plan")
        frames.append(save_response_frame("detail-07-replace-response.png", "Step 7 - replaceproduct: PUT replaces product", replace_args, tool_response_text(cdp, "replaceproduct")))

        update_args = {"product_id": PRODUCT_ID, "body": {"price": 151}}
        set_tool_args_and_call(cdp, "updateproduct", update_args)
        wait_for_tool_response(cdp, "updateproduct", "151")
        frames.append(save_response_frame("detail-08-update-response.png", "Step 8 - updateproduct: PATCH updates price", update_args, tool_response_text(cdp, "updateproduct")))

        list_args = {"limit": 20}
        set_tool_args_and_call(cdp, "listproducts", list_args)
        wait_for_tool_response(cdp, "listproducts", PRODUCT_ID)
        frames.append(save_response_frame("detail-09-list-response.png", "Step 9 - listproducts: GET list shows update", list_args, tool_response_text(cdp, "listproducts")))

        delete_args = {"product_id": PRODUCT_ID}
        set_tool_args_and_call(cdp, "deleteproduct", delete_args)
        wait_for_tool_response(cdp, "deleteproduct", "Replaced video plan")
        frames.append(save_response_frame("detail-10-delete-response.png", "Step 10 - deleteproduct: DELETE returns removed product", delete_args, tool_response_text(cdp, "deleteproduct")))
        cdp.close()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except record_ui.subprocess.TimeoutExpired:
            process.kill()

    mp4, avi = save_video(frames)
    manifest = {
        "frontend_url": FRONTEND_URL,
        "product_id": PRODUCT_ID,
        "frames": [str(frame) for frame in frames],
        "mp4_proof": str(mp4) if mp4 else None,
        "fallback_avi_proof": str(avi),
        "ffmpeg_path": str(record_ui.find_ffmpeg()) if record_ui.find_ffmpeg() else None,
        "mp4_sha256": hashlib.sha256(mp4.read_bytes()).hexdigest() if mp4 else None,
        "avi_sha256": hashlib.sha256(avi.read_bytes()).hexdigest(),
    }
    manifest_path = OUTPUT_DIR / "detailed-ui-proof-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

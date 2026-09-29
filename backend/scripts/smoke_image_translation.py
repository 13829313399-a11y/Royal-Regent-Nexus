"""Synthetic local server inference; never connects to an external translation API."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader
from app.services.document_tools.image_translation import convert_image_translation, runtime_status


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1000, 600), "#ffffff")
    draw = ImageDraw.Draw(image)
    font = next((path for path in ("C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") if Path(path).is_file()), None)
    draw.text((80, 150), "Hello world", font=ImageFont.truetype(font, 60) if font else ImageFont.load_default(60), fill="black")
    draw.text((80, 280), "Quantity 123", font=ImageFont.truetype(font, 50) if font else ImageFont.load_default(50), fill="black")
    source = root / "source.png"
    image.save(source)
    print(json.dumps(runtime_status()), flush=True)
    result = convert_image_translation(source, {"translation_direction": "en_to_zh", "translation_engine": "offline"}, root / "result", lambda stage, current, total: print(stage, current, total, flush=True), lambda: False)
    output = next(file["path"] for file in result.files if file["format"] == "pdf")
    pdf = PdfReader(output)
    assert len(pdf.pages) == 1
    assert abs(float(pdf.pages[0].mediabox.width) / float(pdf.pages[0].mediabox.height) - 1000 / 600) < .001
    records = [{"original": block.original_text, "translated": block.text} for block in result.ir.blocks if block.kind != "image"]
    assert records, "Real model did not detect any text"
    assert any(any('\u4e00' <= char <= '\u9fff' for char in item['translated']) for item in records)
    (root / "report.json").write_text(json.dumps({"pages": 1, "width": 1000, "height": 600, "text": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("REAL_SERVER_INFERENCE_PASSED", flush=True)


if __name__ == "__main__":
    main()

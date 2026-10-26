"""Synthetic source pages; no business record or cloud model involved."""
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter


def scan_image(blur=False):
    image = Image.new('RGB', (1200, 800), 'white')
    draw = ImageDraw.Draw(image)
    path = Path('C:/Windows/Fonts/msyh.ttc')
    font = ImageFont.truetype(str(path), 42) if path.is_file() else ImageFont.truetype('DejaVuSans.ttf', 42)
    draw.text((80, 90), 'SYN-F003 synthetic scan', font=font, fill='black')
    draw.text((140, 300), 'Quantity 4?0', font=font, fill='black')
    if blur:
        box = (140,300,520,360)
        image.paste(image.crop(box).filter(ImageFilter.GaussianBlur(1.4)),box)
    return image


def image_bytes(extension='PNG', blur=False):
    target=BytesIO(); scan_image(blur).save(target,format=extension)
    return target.getvalue()


def scanned_pdf():
    first=Image.new('RGB',(1200,800),'white')
    draw=ImageDraw.Draw(first); draw.text((80,100),'SYN-F003 page one',fill='black',font_size=42)
    target=BytesIO()
    first.save(target,format='PDF',resolution=144,save_all=True,append_images=[scan_image(True)])
    return target.getvalue()

"""Local-only quote-name translation. Non-Chinese specification text is immutable."""
from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Callable, Sequence

from app.services.document_translation import DocumentTranslationError, translate_texts_locally

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
# Specific manufacturing phrases precede shorter terms. Never infer dimensions,
# polarity, materials, price or quantity from the model's answer.
TERMS = {
    "神奇泡泡萌宠": "Magical Bubble Pets", "焕彩变身": "Color Transformation",
    "双人套装报价": "Duo Set Quotation", "拆解报价": "Cost Breakdown",
    "標準正負極鐵電池叻片": "Standard Positive-Negative Iron Battery Contact",
    "標準負正極鐵電池叻片": "Standard Negative-Positive Iron Battery Contact",
    "標準負極鐵電池叻片": "Standard Negative Iron Battery Contact",
    "標準正極電池片": "Standard Positive Battery Contact",
    "雙面背膠": "Double-sided Adhesive", "双面背胶": "Double-sided Adhesive",
    "單面電鍍": "Single-sided Plating", "藍色覆膜面": "Blue Protective Film Side",
    "單面背膠": "Single-sided Adhesive", "單面": "Single-sided", "单面": "Single-sided",
    "強力磁鐵": "Strong Magnet", "强力磁铁": "Strong Magnet", "強力": "Strong", "强力": "Strong",
    "魚絲線": "Fishing Line", "線徑": "Wire Diameter", "線號": "Line Size",
    "日本進口": "Imported from Japan", "尼龙": "Nylon", "尼龍": "Nylon",
    "配重塊": "Counterweight", "配重块": "Counterweight", "琴線": "Piano Wire",
    "電池片": "Battery Contact", "电池片": "Battery Contact",
    "正負極": "Positive-Negative", "負正極": "Negative-Positive",
    "正極": "Positive", "負極": "Negative", "標準": "Standard",
    "硅胶按键": "Silicone Button", "硅膠": "Silicone", "硅胶": "Silicone",
    "丝印": "Screen Printing", "絲印": "Screen Printing",
    "線圈": "Coil", "线圈": "Coil", "自繞": "Self-wound", "線餅": "Flat Coil",
    "水溶膜": "Water-soluble Film", "厚度": "Thickness", "鏡面": "Mirror Surface", "镜面": "Mirror Surface",
    "雪梨纸": "Tissue Paper", "雙面印深藍": "Double-sided Dark Blue Printing",
    "双铜": "Coated Art Paper", "印刷": "Printing", "專色": "Spot Colors", "专": "Spot Colors",
    "模切整张出货": "Die-cut and Supplied in Full Sheets", "書紙": "Woodfree Paper",
    "密封圈": "Sealing Ring", "膠袋": "Poly Bag", "胶水": "Glue", "胶针": "Plastic Fastener",
    "貼纸": "Sticker", "產品": "Product", "产品": "Product", "主机": "Main Unit",
    "电子": "Electronics", "公仔": "Figure", "小瓶": "Small Bottle",
    "粉盒": "Compact", "开关帽": "Switch Cap", "铰链": "Hinge", "电池门": "Battery Door",
    "透明": "Clear", "水樽": "Bottle", "翘翘板": "Seesaw", "前支架": "Front Bracket", "后支架": "Rear Bracket",
    "防水塞": "Waterproof Plug", "配件": "Accessory", "香味環": "Scent Ring", "瓶身": "Bottle Body",
    "瓶底": "Bottle Base", "球托": "Ball Support", "螺母塞组件": "Nut Plug Assembly",
    "椭圆": "Oval", "燈蓋": "Light Cover", "蓋": "Cover", "盖": "Cover", "面": "Front", "底": "Base",
    "光軸": "Smooth Shaft", "軸": "Shaft", "鐵": "Iron", "圈": "Turns", "寸": "in",
    "黑色": "Black", "雙面": "Double-sided", "型": "Type",
}
TERM_PATTERN = re.compile("|".join(re.escape(t) for t in sorted(TERMS, key=len, reverse=True)))
_MODEL_SLOT = threading.BoundedSemaphore(1)


def translate_quote_descriptions(
    texts: Sequence[str], *, model_dir: str | Path, device: str = "cpu",
    translator: Callable[[Sequence[str]], Sequence[str]] | None = None,
) -> dict:
    if not texts or len(texts) > 200 or any(not t.strip() or len(t) > 1000 for t in texts) or sum(map(len, texts)) > 20000:
        raise ValueError("每次最多翻译 200 个名称、共 20,000 字符，单个名称不超过 1,000 字符。")
    # Keep all original non-Chinese tokens; only CJK fragments are
    # eligible for dictionary/model replacement. Long numeric specs never enter inference.
    def known_phrase(match: re.Match) -> str:
        translated = TERM_PATTERN.sub(lambda m: f" {TERMS[m[0]]} ", match[0])
        # Unknown phrases go to the model as a whole. Do not turn a word such
        # as 表面处理 into unrelated fragments by translating just 面.
        return match[0] if CJK.search(translated) else translated
    prepared = [CJK.sub(known_phrase, text) for text in texts]
    pending = list(dict.fromkeys(fragment for text in prepared for fragment in CJK.findall(text)))
    translations: dict[str, str] = {}
    warning = ""
    if pending:
        acquired = _MODEL_SLOT.acquire(blocking=False)
        if not acquired:
            warning = "离线翻译正在处理其他请求，常用术语已翻译；剩余名称可稍后重试。"
        else:
            try:
                values = list(translator(pending) if translator else translate_texts_locally(
                    pending, "zh_to_en", model_dir=model_dir, device=device,
                ))
                if len(values) != len(pending):
                    raise DocumentTranslationError("翻译结果数量不一致。")
                for source, translated in zip(pending, values, strict=True):
                    # A model must not invent specifications or silently erase text.
                    if isinstance(translated, str) and len(translated) <= 1000 and re.fullmatch(r"[A-Za-z][A-Za-z '\-,.()]*", translated.strip()):
                        translations[source] = translated.strip()
            except DocumentTranslationError:
                warning = "离线翻译模型暂不可用，常用术语已翻译；剩余名称保留原文，可重试或手工核对。"
            finally:
                _MODEL_SLOT.release()
    rows = []
    for source, text in zip(texts, prepared, strict=True):
        translated = re.sub(r"[ \t]+", " ", CJK.sub(lambda m: f" {translations[m[0]]} " if m[0] in translations else m[0], text)).strip()
        rows.append({"source": source, "translation": translated, "needs_review": bool(CJK.search(translated))})
    if not warning and any(row["needs_review"] for row in rows):
        warning = "部分名称未获得有效英文译文，已保留原文，请重试或核对。"
    return {"items": rows, "warning": warning, "engine": "local"}

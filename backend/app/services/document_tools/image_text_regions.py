"""Native PDF words, in raster coordinates; no OCR guesses for native numbers."""
import re


PROTECTED = re.compile(r"\d|https?://|www\.|@|^[#＃]|^(?:PANTONE|UPC|CE|CPSC|ASTM|EN|ISO|AQL|MIL|QA|QC|PVC|ABS|PP|PET|PE|BR|EEC|EC|EU|USA|S/S|PNP|PUP|HOLOLIVE|JAKKS|PEANUTS|TM|Sa|Cr|Maj|Min)$", re.I)


def protected(text):
    return bool(PROTECTED.search(text) or (not re.search(r"[A-Za-z\u3400-\u9fff]", text) and text not in {'&','/','(',')','-'}))


def native_regions(page, scale):
    """Split at measured spaces, column boundaries and protected words.

    Use the existing normalized visible-page PDF. Native words own exact boxes;
    protected words never enter translation or erasure, including inline values.
    """
    words = page.dedupe_chars(tolerance=.4).extract_words(x_tolerance=1.5, y_tolerance=2,
                                                       extra_attrs=['fontname', 'size'])
    regions, groups = [], []
    for word in sorted(words, key=lambda w: (round(w['top'] / 2) * 2, w['x0'])):
        text = word['text'].strip()
        if not text or re.fullmatch(r'[_─—=]{3,}', text):
            continue
        keep = protected(text) or not word.get('upright', True) or '\ufffd' in text or '(cid:' in text
        prior = groups[-1][-1] if groups else None
        if (not keep and prior and not prior['_keep'] and abs(word['top'] - prior['top']) < 2
                and -.5 <= word['x0'] - prior['x1'] <= max(7, word['size'] * .9)
                and abs(word['size'] - prior['size']) < 1):
            groups[-1].append({**word, '_keep': keep})
        else:
            groups.append([{**word, '_keep': keep}])
    for group in groups:
        x0, top = min(w['x0'] for w in group), min(w['top'] for w in group)
        x1, bottom = max(w['x1'] for w in group), max(w['bottom'] for w in group)
        regions.append({'id': f'native-{len(regions)}', 'sourceText': ' '.join(w['text'] for w in group),
                        'box': {'x': x0 * scale, 'y': top * scale, 'width': (x1-x0)*scale, 'height': (bottom-top)*scale},
                        'fontSize': max(w['size'] for w in group)*scale, 'bold': any('bold' in w['fontname'].lower() for w in group),
                        'protected': group[0]['_keep'], 'method': 'native', 'prob': 1})
    return regions

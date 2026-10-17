# Ported from huakang-jp-entry d82c172; server-only adapter, no desktop startup.
# -*- coding: utf-8 -*-
"""解析 JP 客订单邮件（eml / 粘贴的 HTML 正文），提取订单行。"""
import re
import email
import html as html_lib
from datetime import datetime, date, timedelta
from email.header import decode_header, make_header
from html.parser import HTMLParser

LONG_CODE_RE = re.compile(r'\b(\d{5})-([A-Z0-9]{2,4})-([A-Z0-9]{1,2})-(\d{3})-([A-Z0-9]{2,4})\b', re.I)
BABY_CODE_RE = re.compile(r'^\d{5}$')

MONTH_EN = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
            'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}

COUNTRY_MAP = {
    'uk': '英国', 'united kingdom': '英国', 'britain': '英国',
    'usa': '美国', 'us': '美国', 'united states': '美国', 'america': '美国',
    'israel': '以色列', 'poland': '波兰', 'germany': '德国', 'france': '法国',
    'spain': '西班牙', 'italy': '意大利', 'netherlands': '荷兰', 'holland': '荷兰',
    'belgium': '比利时', 'venezuela': '委内瑞拉', 'mexico': '墨西哥',
    'canada': '加拿大', 'australia': '澳大利亚', 'japan': '日本',
    'korea': '韩国', 'russia': '俄罗斯', 'brazil': '巴西', 'chile': '智利',
    'colombia': '哥伦比亚', 'peru': '秘鲁', 'argentina': '阿根廷',
    'uae': '阿联酋', 'dubai': '迪拜', 'saudi': '沙特', 'turkey': '土耳其',
    'sweden': '瑞典', 'norway': '挪威', 'denmark': '丹麦', 'finland': '芬兰',
    'austria': '奥地利', 'switzerland': '瑞士', 'portugal': '葡萄牙',
    'greece': '希腊', 'czech': '捷克', 'hungary': '匈牙利', 'romania': '罗马尼亚',
    'south africa': '南非', 'new zealand': '新西兰', 'singapore': '新加坡',
    'malaysia': '马来西亚', 'thailand': '泰国', 'philippines': '菲律宾',
    'indonesia': '印尼', 'vietnam': '越南', 'india': '印度',
}


class TableParser(HTMLParser):
    """把 HTML 里的 <table> 全部抽成行列表格。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.table_positions = []  # 每个 <table> 的 (行, 列)，用于定位引用历史
        self._table = None
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self._table = []
            self.tables.append(self._table)
            self.table_positions.append(self.getpos())
        elif tag == 'tr' and self._table is not None:
            self._row = []
        elif tag in ('td', 'th') and self._row is not None:
            self._cell = []
        elif tag == 'br' and self._cell is not None:
            self._cell.append(' ')

    def handle_endtag(self, tag):
        if tag == 'table':
            self._table = None
        elif tag == 'tr' and self._row is not None:
            if self._table is not None:
                self._table.append(self._row)
            self._row = None
        elif tag in ('td', 'th') and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r'\s+', ' ', ' '.join(self._cell)).strip())
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def html_to_tables(html_text):
    p = TableParser()
    p.feed(html_text)
    return p.tables


def html_to_tables_pos(html_text):
    """同 html_to_tables，但额外返回每个表格在原文中的绝对字符位置。"""
    p = TableParser()
    p.feed(html_text)
    line_starts = [0]
    for m in re.finditer('\n', html_text):
        line_starts.append(m.end())
    offs = []
    for ln, col in p.table_positions:
        base = line_starts[ln - 1] if ln - 1 < len(line_starts) else 0
        offs.append(base + col)
    return p.tables, offs


def html_to_text(html_text):
    text = re.sub(r'(?is)<(script|style).*?</\1>', ' ', html_text)
    text = re.sub(r'(?is)<br\s*/?>', '\n', text)
    text = re.sub(r'(?is)</(p|div|tr|table|li|h\d)>', '\n', text)
    text = re.sub(r'(?is)<[^>]+>', ' ', text)
    text = html_lib.unescape(text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n+', '\n', text)
    return text.strip()


def decode_mime_header(s):
    if not s:
        return ''
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s


def parse_eml(data):
    """从 eml 字节中提取 (html, subject, date)。优先 text/html，没有则用 text/plain。"""
    msg = email.message_from_bytes(data)
    subject = decode_mime_header(msg.get('Subject', ''))
    date_str = msg.get('Date', '')
    ref_date = None
    try:
        dt = email.utils.parsedate_to_datetime(date_str)
        ref_date = dt  # 保留时分秒，线程去重时比较新旧用
    except Exception:
        pass
    html_part, text_part = None, None
    for part in msg.walk():
        if part.get_filename():
            continue
        ct = part.get_content_type()
        if ct == 'text/html' and html_part is None:
            payload = part.get_payload(decode=True)
            if payload:
                html_part = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
        elif ct == 'text/plain' and text_part is None:
            payload = part.get_payload(decode=True)
            if payload:
                text_part = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
    return html_part, text_part, subject, ref_date


def norm_header(h):
    return re.sub(r'[^a-z0-9一-鿿]+', ' ', h.lower()).strip()


def normalize_subject(subject):
    """归一化邮件主题，用于识别同一订单线程的多次转发/回复。"""
    s = decode_mime_header(subject or '')
    s = re.sub(r'(?i)^\s*((fw|fwd|re|回复|转发)\s*[:：]\s*)+', '', s)
    s = re.sub(r'[^a-z0-9一-鿿]+', '', s.lower())
    return s


def find_col(headers, includes, excludes=()):
    for i, h in enumerate(headers):
        hn = norm_header(h)
        if all(k in hn for k in includes) and not any(k in hn for k in excludes):
            return i
    return None


def parse_date_str(s, ref_date):
    """把 11/12、11/12/2026、25-Oct、Oct 25 之类的日期解析成 date。"""
    if not s:
        return None
    s = s.strip().strip('.,;:')
    if '>' in s:  # 8/10>8/21 取改后日期
        s = s.split('>')[-1].strip()
    m = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', s)
    if m:
        mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return _safe_date(y, mo, d)
    m = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', s)
    if m:
        return _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r'^(\d{1,2})/(\d{1,2})$', s)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        return _safe_date(_infer_year(mo, ref_date), mo, d)
    m = re.match(r'^(\d{1,2})\s*[-\s]\s*([A-Za-z]{3,})\.?$', s)
    if m and m.group(2).lower()[:3] in MONTH_EN:
        d, mo = int(m.group(1)), MONTH_EN[m.group(2).lower()[:3]]
        return _safe_date(_infer_year(mo, ref_date), mo, d)
    m = re.match(r'^([A-Za-z]{3,})\s*[-\s]\s*(\d{1,2})$', s)
    if m and m.group(1).lower()[:3] in MONTH_EN:
        mo, d = MONTH_EN[m.group(1).lower()[:3]], int(m.group(2))
        return _safe_date(_infer_year(mo, ref_date), mo, d)
    return None


def _infer_year(month, ref_date):
    ref = ref_date or date.today()
    return ref.year + 1 if month < ref.month - 1 else ref.year


def _safe_date(y, m, d):
    try:
        return date(y, m, d)
    except ValueError:
        return None


def fmt_date(d):
    return f'{d.year}/{d.month}/{d.day}' if d else ''


def hangq_from_sd(sd):
    """行Q期 = 截数期（走货期）前一周；落在周三/周六/周日则继续往前挪到最近的工作日。"""
    if not sd:
        return None
    d = sd - timedelta(days=7)
    while d.weekday() in (2, 5, 6):  # 周三、周六、周日
        d -= timedelta(days=1)
    return d


def norm_carton(v):
    """装箱数归一为整数字符串。返回 (值, 是否发生了取整)：
    '6' / '6.0' → ('6', False)；数量除不尽产生的小数如 '334.67' → ('335', True)。"""
    s = str(v or '').strip()
    if not s:
        return '', False
    try:
        f = float(s)
    except ValueError:
        return s, False
    if f == int(f):
        return str(int(f)), False
    return str(round(f)), True


SIGN_LINE_RE = re.compile(r'(regard|thanks|tel[:：]|mobile|wechat|@|http|请查收|'
                          r'ltd\.|company|工业|有限公司|工厂地址)', re.I)


def _strip_signature_lines(text):
    lines = [l.strip() for l in text.split('\n')]
    kept = [l for l in lines if l and not SIGN_LINE_RE.search(l) and len(l) > 1]
    return ' '.join(kept).strip()


def extract_thread_date(full_text):
    """从转发/回复头里提取最新一封的日期时间（Foxmail 的 '| Date | 9/9/2026 10:14 |'
    或中文 '发送时间：2026-09-10 10:45'），取文本中最先出现的一个。"""
    best = None
    m = re.search(r'\bDate\b\s*[|：:]?\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})', full_text)
    if m:
        mo, d, y, hh, mm = map(int, m.groups())
        if d > 12 and mo <= 12:  # M/d/yyyy
            pass
        best = _safe_datetime(y, mo, d, hh, mm)
    m2 = re.search(r'发送时间[:：]\s*(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})', full_text)
    if m2:
        y, mo, d, hh, mm = map(int, m2.groups())
        dt = _safe_datetime(y, mo, d, hh, mm)
        if dt and (best is None or m2.start() < m.start()):
            best = dt
    return best


def _safe_datetime(y, mo, d, hh, mm):
    try:
        return datetime(y, mo, d, hh, mm)
    except ValueError:
        return None


def newest_reply_text(full_text):
    """取最新回复所在的文本段：从头（含转发头，转发头里无订单关键词，无害）
    到引用历史开始（发件人：/Original Message/Replied Message/On wrote/第二个 Forwarded 标记）。"""
    cut = len(full_text)
    fwd = list(re.finditer(r'-{3,}\s*Forwarded Message\s*-{3,}', full_text, re.I))
    if len(fwd) > 1:
        cut = fwd[1].start()
    for pat in (r'-{3,}\s*(Original|Replied) Message', r'发件人[:：]', r'发送时间[:：]',
                r'From\s*[:：]', r'On .{0,80}wrote[:：]?'):
        m2 = re.search(pat, full_text, re.I)
        if m2 and m2.start() < cut:
            cut = m2.start()
    return full_text[:cut]


def extract_reply_info(reply_text, ref_date):
    """从最新回复文字中提取 DDD、S/D、包装、备注行、#货号 单行备注。"""
    info = {'ddd': '', 'sd': None, 'pkg': '', 'global_notes': [], 'item_notes': {}}
    m = re.search(r'DDD\s*[:/]?\s*(\d{1,2}/\d{1,2}(?:\s*>\s*\d{1,2}/\d{1,2})?)', reply_text, re.I)
    if m:
        info['ddd'] = 'DDD ' + m.group(1).replace(' ', '')
    m = re.search(r'(?:S/D|货期)\s*[:/]?\s*(\d{1,2}/\d{1,2}(?:/\d{4})?)', reply_text, re.I)
    if m:
        d = parse_date_str(m.group(1), ref_date)
        if d:
            info['sd'] = d
    m = re.search(r'\b(\d+L|EN)\b\s*pkg', reply_text, re.I)
    if m:
        info['pkg'] = m.group(1).upper()
    for line in reply_text.split('\n'):
        line = line.strip().strip('|').strip()
        if not line or len(line) < 4:
            continue
        if re.match(r'(?i)^(subject|from|to|cc|date|sent)\b', line):
            continue  # 转发头行
        # 含 #货号 的行：备注挂到行内提到的每个货号（#38757 28452 88333 这种连写也算）
        codes = re.findall(r'#(\d{5})\b', line)
        if codes:
            codes += [c for c in re.findall(r'\b(\d{5})\b', re.sub(r'#\d{5}\b', '', line))]
            note = re.sub(r'#?\d{5}\b', '', line)
            note = re.sub(r'^请查收附件\s*', '', note)
            note = re.sub(r'谢谢[！!]*\s*$', '', note)
            note = re.sub(r'\s+', ' ', note).strip(' ,，;；.&')
            if note and note.upper() != 'MA':  # "请查收附件#93014 MA,谢谢" 剩下的 MA 是噪音
                for c in dict.fromkeys(codes):
                    info['item_notes'].setdefault(c, []).append(note)
            continue
        if re.search(r'(MOQ|surcharge|附加费|component|要在.{0,12}送|运输)', line, re.I):
            note = re.sub(r'\s+', ' ', line)
            # 跳过表头单词行和签名行
            if SIGN_LINE_RE.search(note) or re.match(r'^[A-Za-z ]{1,20}$', note):
                continue
            info['global_notes'].append(note)
    return info


def pick_country(text):
    if not text:
        return ''
    t = text.lower().strip()
    if t in COUNTRY_MAP:
        return COUNTRY_MAP[t]
    for k, v in COUNTRY_MAP.items():
        if re.search(r'\b' + re.escape(k) + r'\b', t):
            return v
    return ''


SUBJECT_SKIP = ('just play', 'royal regent', 'order enquiry', 'new order', 'enquiry',
                'fw', 're', 'huakang', 'rr', 'jp')


def customer_from_subject(subject):
    s = re.sub(r'^(fw|re|fwd)\s*[:：]\s*', '', subject or '', flags=re.I)
    for token in re.split(r'[/\-_–—]', s):
        token = token.split(',')[0].strip()
        if not token:
            continue
        token = re.sub(r'^RR\s+', '', token, flags=re.I)  # 去掉 RR 前缀
        low = token.lower()
        if low in SUBJECT_SKIP or low.startswith(('just play', 'royal regent', 'order enq',
                                                  'new order', 'rr')):
            continue
        if re.match(r'^\d{5}', token) or re.search(r'schk|\d{6,}', token, re.I):
            continue
        token = re.sub(r'#.*$', '', token)
        # 去掉 "order enquiry/inquiry" 及之后的部分（JP/WMUS 客的主题习惯）
        token = re.sub(r'\s+(new\s+)?order\s+(enq|inq)\w*.*$', '', token, flags=re.I).strip()
        token = re.sub(r'\s+f\d{4}$', '', token, flags=re.I).strip()
        token = re.sub(r'\s+wk\s*\d+$', '', token, flags=re.I).strip()  # "WMUS wk36" → WMUS
        token = re.sub(r'\s*\((import order|import)\)\s*$', '', token, flags=re.I)
        if re.match(r'^[A-Za-z0-9 &().+]{2,40}$', token):
            return token
    return ''


def normalize_note(note):
    """备注按文员习惯清洗：散件翻译、去掉无信息量的 'no MOQ issue' 类废话。"""
    note = (note or '').strip()
    if not note:
        return ''
    # 附加费样板说明（金额已由"运输附加费用USD xxx"携带）
    if re.match(r'(?i)extra shipment surcharge', note):
        return ''
    # All component要在12/22送到 → 散件12/22送到
    note = re.sub(r'(?i)all\s+compon\w*\s*要在\s*([\d/]+)\s*送到', r'散件\1送到', note)
    # 8L pkg. / 8L pkg 这种包装说明不进备注（版本列已有）
    note = re.sub(r'(?i)\b\d+L\b\s*pkg\.?\s*', '', note)
    # no MOQ issue 无信息量
    note = re.sub(r'(?i)([,.，;；]?\s*(no\s+)?mo\s*moq\s+issue[.!]?)+', '', note)
    note = re.sub(r'(?i)^\s*no\s+moq\s+issue[.!]?\s*$', '', note)
    note = note.strip(' ,，;；.')
    # 文员不把议价性备注录进订单备注：纯 MOQ 数字、can tag on 拼单说明
    if re.fullmatch(r'(?i)(production\s*/?\s*(pkg\s*)?)?moq\s*[\d,.]+\s*k?\.?', note):
        return ''
    if re.match(r'(?i)can tag on\b', note):
        return ''
    return note


def clean_item_code(raw):
    """'89944-VAL-2A-006-OPB> 89786-000-3A-006-OPP' 取 '>' 之后的新货号。"""
    if not raw:
        return None, None
    part = raw.split('>')[-1].strip()
    # 客人粘贴时货号里可能带空格/换行（'67053 -000-2B-003-WB0'），先收紧再匹配
    tight = re.sub(r'(?<=[\dA-Za-z])\s+(?=[-\dA-Za-z])', '', part)
    m = LONG_CODE_RE.search(tight)
    if m:
        return m.group(1), m.group(0).upper()
    return None, None


def is_order_table(table):
    """判断表格是不是订单明细表：某列数据含长货号，且表头有数量列。"""
    if len(table) < 2:
        return False
    header = table[0]
    joined = ' '.join(header)
    if not LONG_CODE_RE.search(' '.join(' '.join(r) for r in table[1:])):
        return False
    if find_col(header, ['qty']) is None and find_col(header, ['quantity']) is None \
            and find_col(header, ['order qty']) is None:
        return False
    return True


def _has_long_code(v):
    """单元格是否含长货号（容忍粘贴带入的空格）。"""
    if not v or not LONG_CODE_RE.search(v):
        tight = re.sub(r'(?<=[\dA-Za-z])\s+(?=[-\dA-Za-z])', '', v or '')
        return bool(LONG_CODE_RE.search(tight))
    return True


PO_CELL_RE = re.compile(r'^\d{8,12}$')
SCHK_CELL_RE = re.compile(r'(?i)^SCHK[-\s]?[\d-]')
NUM_CELL_RE = re.compile(r'^[\d,]+(\.\d+)?$')

# 无标题订单表（JP/WMUS 客直接把 Excel 区域粘进正文，没有表头行）：
# 行内有长货号 + 数量列即可识别，列角色按内容推断
_QUOTED_MARK_RE = re.compile(
    r'(replied message|original message|原始邮件|转发的邮件|发件人[:：]|发送时间[:：]'
    r'|on .{0,80}wrote)', re.I)


class QuantityColumnRequired(ValueError):
    def __init__(self, table_index, table):
        super().__init__("无表头订单有多个数字列，请明确选择数量列")
        self.table_index, self.table = table_index, table


def _headerless_order_tables(html_text, quantity_columns=None, allow_quoted=False):
    """找出最新回复区域内的无标题订单表，返回 [(table, cols)]。
    引用历史（Replied/Original Message 之后）里的重复表格不算。"""
    tables, offs = html_to_tables_pos(html_text)
    m = _QUOTED_MARK_RE.search(html_text)
    cut = m.start() if m else len(html_text)
    out = []
    for table_index, (t, off) in enumerate(zip(tables, offs)):
        if off > cut and (not allow_quoted or out):
            continue
        try:
            cols = _infer_headerless_cols(t, (quantity_columns or {}).get(table_index))
        except ValueError:
            raise QuantityColumnRequired(table_index, t)
        if cols:
            cols['quoted_source'] = off > cut
            out.append((t, cols))
            if off > cut:
                break  # Explicit current updates may use only the nearest table.
    # Without explicit current shipping/package updates, quoted history is not
    # a new enquiry. Never import all historical tables in a mail chain.
    return out


def _infer_headerless_cols(table, quantity_column=None):
    """按列内容推断无标题订单表的列角色（item/qty 必须有），推不出来返回 None。"""
    rows = [r for r in table if any((c or '').strip() for c in r)]
    if not rows:
        return None
    ncols = max(len(r) for r in rows)

    def vals(i):
        return [(r[i] or '').strip() for r in rows if i < len(r) and (r[i] or '').strip()]

    col_item, best = None, 0
    for i in range(ncols):
        n = sum(1 for v in vals(i) if _has_long_code(v))
        if n > best:
            best, col_item = n, i
    if col_item is None or best < 1:
        return None
    min_hits = min(2, best)

    def best_col(pred, exclude, min_hits=min_hits):
        bi, bn = None, 0
        for i in range(ncols):
            if i in exclude:
                continue
            n = sum(1 for v in vals(i) if pred(v))
            if n > bn:
                bi, bn = i, n
        return bi if bn >= min_hits else None

    col_po = best_col(lambda v: bool(PO_CELL_RE.match(v)), {col_item})
    col_so = best_col(lambda v: bool(SCHK_CELL_RE.match(v)),
                      {x for x in (col_item, col_po) if x is not None})
    excluded = {x for x in (col_item, col_po, col_so) if x is not None}
    numeric = [i for i in range(ncols) if i not in excluded
               and sum(bool(NUM_CELL_RE.fullmatch(v)) for v in vals(i)) >= min_hits]
    if quantity_column is not None:
        if quantity_column not in numeric:
            raise ValueError("所选数量列不是有效数字列")
        col_qty = quantity_column
    elif len(numeric) > 1:
        raise ValueError("数量列有歧义")
    else:
        col_qty = numeric[0] if numeric else None
    if col_qty is None:
        return None
    used = {x for x in (col_item, col_po, col_so, col_qty) if x is not None}
    col_baby = best_col(lambda v: bool(re.match(r'^\d{5}(\s|$)', v)), used)
    if col_baby is not None:
        used.add(col_baby)
    col_desc, best_len = None, 0
    for i in range(ncols):
        if i in used:
            continue
        vs = vals(i)
        if len(vs) < 2:
            continue
        avg = sum(len(v) for v in vs) / len(vs)
        alpha = sum(1 for v in vs if re.search(r'[A-Za-z]', v))
        if alpha >= 2 and avg > best_len:
            col_desc, best_len = i, avg
    return {'item': col_item, 'qty': col_qty, 'po': col_po, 'so': col_so,
            'baby': col_baby, 'desc': col_desc}


def _parse_headerless_table(table, cols, source, warnings, reply_info, ref_date):
    """按推断出的列角色解析无标题订单表；合计行/空行自动跳过。"""
    def cell(row, idx):
        if idx is None or idx >= len(row):
            return ''
        return (row[idx] or '').strip()

    orders = []
    last_po = ''
    for row in table:
        if not any((c or '').strip() for c in row):
            continue
        baby, long_code = clean_item_code(cell(row, cols['item']))
        pkg = ''
        m = re.match(r'^(\d{5})\b\s*(.+)?$', cell(row, cols['baby']))
        if m:
            if not baby:
                baby = m.group(1)
                warnings.append(f'【{source}】货号 {baby} 缺少长货号/规格，请人工核对')
            if m.group(2):
                pkg = m.group(2).strip()
        qty = cell(row, cols['qty']).replace(',', '')
        if not baby or qty is None:
            continue  # 合计行（只有数量）或无法识别的行
        po = cell(row, cols['po']) or last_po
        if cell(row, cols['po']):
            last_po = cell(row, cols['po'])
        if po.upper() in ('TBC', 'TBA'):
            po = ''
        sd = reply_info['sd']
        notes = []
        if baby in reply_info['item_notes']:
            notes.extend(reply_info['item_notes'][baby])
        notes = [n for n in (normalize_note(n) for n in notes) if n]
        orders.append({
            'baby_item': baby,
            'long_code': long_code or cell(row, cols['item']),
            'description': cell(row, cols['desc']),
            'qty': qty,
            'pkg': pkg,
            'customer_po': po,
            'customer': '',
            'sales_order': cell(row, cols['so']),
            'ship_date': fmt_date(hangq_from_sd(sd)),
            'cutoff_date': fmt_date(sd),
            'sd_orig': fmt_date(sd),
            'ship_date_source': '回复文字' if sd else '',
            'country': '',
            'item_note': '，'.join(dict.fromkeys(notes)),
        })
    return orders


def parse_order_email(html_text, subject='', ref_date=None, source='', quantity_columns=None):
    """解析一封订单邮件，返回 {orders, warnings, meta}。"""
    warnings = []
    if ref_date is None:
        ref_date = date.today()
    full_text = html_to_text(html_text)
    if not subject:
        m_sub = re.search(r'\bSubject\s*[|：:]?\s*([^\n|]+)', full_text)
        if m_sub:
            subject = m_sub.group(1).strip()
    reply = newest_reply_text(full_text)
    reply_info = extract_reply_info(reply, ref_date)
    thread_dt = extract_thread_date(full_text)
    tables = html_to_tables(html_text)
    positioned, offsets = html_to_tables_pos(html_text)
    quote = _QUOTED_MARK_RE.search(html_text)
    candidates = [t for t, offset in zip(positioned, offsets)
                  if is_order_table(t) and (not quote or offset < quote.start())]
    reuse_quoted = bool(reply_info['sd'] or reply_info['pkg']) and not re.search(
        r'no\s+new\s+orders?|cancel(?:led|ed)?|do\s+not\s+(?:proceed|place)|取消|勿录|不要录|不下单', reply, re.I)
    reused_quoted_table = False
    if not candidates and quote and reuse_quoted:
        quoted = [t for t, offset in zip(positioned, offsets) if offset > quote.start() and is_order_table(t)]
        if quoted:
            candidates = quoted[:1]
            reused_quoted_table = True
            warnings.append(f'【{source}】最新回复明确更新货期或包装，沿用最近引用订单表；请核对回复和表格是否属于本单')

    orders = []
    table_count = len(candidates)
    if candidates:
        table = candidates[0]
        if len(candidates) > 1:
            warnings.append(f'【{source}】检测到 {len(candidates)} 个订单表格（含邮件历史中的旧版本），'
                            f'已取最新一个（{len(table) - 1} 行），请核对是否完整')
        orders = _parse_headered_table(table, source, warnings, reply_info, ref_date)
    else:
        # 无标题行表格（JP/WMUS 客直接粘 Excel 区域进正文）
        hless = _headerless_order_tables(html_text, quantity_columns, allow_quoted=reuse_quoted)
        if not hless:
            return {'orders': [], 'warnings': [f'【{source}】未找到订单表格，请检查邮件内容'],
                    'meta': {'subject': subject}}
        table_count = len(hless)
        reused_quoted_table = any(cols['quoted_source'] for _, cols in hless)
        for t, cols in hless:
            orders.extend(_parse_headerless_table(t, cols, source, warnings, reply_info, ref_date))
        warnings.append(f'【{source}】邮件表格没有标题行，已按列内容自动识别 '
                        f'{table_count} 个表格，请人工核对')

    if not orders:
        warnings.append(f'【{source}】订单表格中没有解析到有效行')

    meta_customer = customer_from_subject(subject)
    meta_country = pick_country(subject)
    pkg_warned = set()
    for o in orders:
        # This path was enabled by an explicit current-reply update, not a
        # current order table. Keep the quoted originals as audit evidence, but
        # never let them silently override the update that enabled reuse.
        if reused_quoted_table:
            o['quoted_original'] = {key: o.get(key, '') for key in ('pkg', 'cutoff_date', 'ship_date')}
            if reply_info['pkg']:
                if o.get('pkg') and o['pkg'].upper() != reply_info['pkg'].upper():
                    warnings.append(f'【{source}】引用表包装 {o["pkg"]} 与最新回复 {reply_info["pkg"]} 不同，已按最新回复更新，请核对')
                o['pkg'] = reply_info['pkg']
            if reply_info['sd']:
                sd = fmt_date(reply_info['sd'])
                if o.get('cutoff_date') and o['cutoff_date'] != sd:
                    warnings.append(f'【{source}】引用表货期 {o["cutoff_date"]} 与最新回复 {sd} 不同，已按最新回复更新，请核对')
                o['sd_orig'] = o['cutoff_date'] = sd
                o['ship_date'] = fmt_date(hangq_from_sd(reply_info['sd']))
                o['ship_date_source'] = '最新回复文字（引用表原值已保留）'
        # 客名以主题里的短名优先（文员习惯，如 Grupo Mas Tres / MORRISONS）
        if meta_customer:
            o['customer'] = meta_customer
        if not o['country']:
            o['country'] = meta_country
        tbl_pkg = str(o.get('pkg') or '').strip()
        reply_pkg = str(reply_info['pkg'] or '').strip()
        if not tbl_pkg:
            o['pkg'] = reply_pkg
        elif reply_pkg and tbl_pkg.upper() != reply_pkg.upper() and tbl_pkg.upper() not in pkg_warned:
            # 客人表格版本与回复确认版本不一致（如表格 8L、回复 3L），仍按表格填，但提示人工确认
            pkg_warned.add(tbl_pkg.upper())
            warnings.append(f'【{source}】版本不一致：客人表格是 {tbl_pkg}，'
                            f'回复中确认的是 {reply_pkg}，已按表格填 {tbl_pkg}，请人工确认')
        if not o['ship_date'] and reply_info['sd']:
            sd = reply_info['sd']
            o['sd_orig'] = fmt_date(sd)
            o['cutoff_date'] = fmt_date(sd)
            o['ship_date'] = fmt_date(hangq_from_sd(sd))
            o['ship_date_source'] = '回复文字'
    # 全局备注同样清洗，并去掉与行备注重复的
    cleaned_global = [n for n in (normalize_note(n) for n in reply_info['global_notes']) if n]
    # 附加费：若全局备注已有（PO 级），去掉行内的同义表内备注，避免重复且保证每行都有
    if any('附加费' in g for g in cleaned_global):
        for o in orders:
            kept = [n for n in o['item_note'].split('，') if n and '附加费' not in n]
            o['item_note'] = '，'.join(kept)
    item_note_set = {n for o in orders for n in o['item_note'].split('，') if n}
    global_notes = []
    for n in dict.fromkeys(cleaned_global):
        if any(n in it or it in n for it in item_note_set):
            continue
        global_notes.append(n)

    meta = {
        'subject': subject,
        'source': source,
        'order_date': fmt_date(thread_dt or ref_date),
        'thread_date': thread_dt.isoformat() if thread_dt else '',
        'customer': meta_customer,
        'country': meta_country,
        'ddd': reply_info['ddd'],
        'global_note': '，'.join(global_notes),
        'sd': fmt_date(reply_info['sd']),
        'table_count': table_count,
    }
    return {'orders': orders, 'warnings': warnings, 'meta': meta}


def _parse_headered_table(table, source, warnings, reply_info, ref_date):
    """解析带表头的订单表（原 parse_order_email 的主流程，原样保留）。"""
    header = table[0]
    col_item = None
    best = 0
    for i in range(len(header)):
        n = sum(1 for r in table[1:] if i < len(r) and LONG_CODE_RE.search(r[i] or ''))
        if n > best:
            best, col_item = n, i
    col_baby = find_col(header, ['baby item'])
    col_qty = find_col(header, ['qty'])
    if col_qty is None:
        col_qty = find_col(header, ['quantity'])
    if col_qty is None:
        col_qty = find_col(header, ['order qty'])
    col_desc = find_col(header, ['description'])
    col_pkg = find_col(header, ['pkg'])
    if col_pkg is None:
        col_pkg = find_col(header, ['package'])
    col_po = find_col(header, ['po no'])
    if col_po is None:
        col_po = find_col(header, ['customer po'])
    if col_po is None:
        col_po = find_col(header, ['po#'])
    if col_po is None:
        col_po = find_col(header, ['po'], excludes=('port', 'just play'))
    col_cust = find_col(header, ['tomer name'])  # 兼容 "Cus+A2:Z3tomer Name" 这种坏表头
    if col_cust is None:
        col_cust = find_col(header, ['customer'], excludes=('po', 'item'))
    col_port = find_col(header, ['port of discharge'])
    col_sd = find_col(header, ['fty sd'])
    col_promised = find_col(header, ['promised crd'])
    if col_promised is not None:
        col_sd = col_promised
    col_so = find_col(header, ['sales order'])
    col_remark = find_col(header, ['remark'])
    col_sur = find_col(header, ['surcharge'], excludes=('extra',))

    def cell(row, idx):
        if idx is None or idx >= len(row):
            return ''
        return (row[idx] or '').strip()

    orders = []
    last_po, last_cust = '', ''
    for row in table[1:]:
        raw_item = cell(row, col_item)
        baby, long_code = clean_item_code(raw_item)
        if not baby:
            # 长货号缺失时，找 Baby Item no 列或行内独立的 5 位货号
            cand = cell(row, col_baby)
            if not BABY_CODE_RE.match(cand or ''):
                cand = ''
                for i, v in enumerate(row):
                    if i in (col_qty, col_item):
                        continue
                    if BABY_CODE_RE.match((v or '').strip()):
                        cand = v.strip()
                        break
            if BABY_CODE_RE.match(cand or ''):
                baby = cand
                warnings.append(f'【{source}】货号 {baby} 缺少长货号/规格，请人工核对')
        qty_raw = cell(row, col_qty)
        qty = qty_raw.replace(',', '')
        if not baby and qty is None:
            continue

        po = cell(row, col_po) or last_po
        cust = cell(row, col_cust) or last_cust
        if cell(row, col_po):
            last_po = cell(row, col_po)
        if cell(row, col_cust):
            last_cust = cell(row, col_cust)
        if po.upper() in ('TBC', 'TBA', ''):  # 客PO 未定（TBC）时文员留空
            po = ''

        sd = parse_date_str(cell(row, col_sd), ref_date)
        sd_source = '表内'
        if not sd:
            sd = reply_info['sd']
            sd_source = '回复文字' if sd else ''
        # 文员规律：货期填截数期；行Q期D = 截数期前一周，且避开周三/周末
        hangq = hangq_from_sd(sd)

        country = pick_country(cell(row, col_port))

        notes = []
        # 行缺单元格时（HTML 省略空 td）Remark/Surcharge 列会错位，只有满列行才读
        if len(row) >= len(header):
            sur = cell(row, col_sur)
            if sur and sur not in ('0', '0.00'):
                notes.append(f'运输附加费用USD {sur}')
            remark = cell(row, col_remark)
            if remark and not re.match(r'(?i)extra shipment surcharge', remark):
                notes.append(remark)
        if baby and baby in reply_info['item_notes']:
            notes.extend(reply_info['item_notes'][baby])
        notes = [n for n in (normalize_note(n) for n in notes) if n]

        orders.append({
            'baby_item': baby or '',
            'long_code': long_code or raw_item,
            'description': cell(row, col_desc),
            'qty': qty if qty is not None else '',
            'pkg': cell(row, col_pkg),
            'customer_po': po,
            'customer': cust,
            'sales_order': cell(row, col_so),
            'ship_date': fmt_date(hangq),
            'cutoff_date': fmt_date(sd),
            'sd_orig': fmt_date(sd),
            'ship_date_source': sd_source,
            'country': country,
            'item_note': '，'.join(dict.fromkeys(notes)),
        })
    return orders

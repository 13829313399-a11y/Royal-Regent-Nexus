# Ported from huakang-jp-entry d82c172; server-only adapter, no desktop startup.
# -*- coding: utf-8 -*-
"""货价表：货号 → 客货价（HK$），按货运类别（柜货/出厂价/散货/客派车）取最新一条。

数据来自《生产货号货价浏览总表.xlsx》；此服务适配版仅在任务内存中读取，
参照版本由订单中心数据库保留，不写桌面工具的数据文件。
"""
import os
import re
from datetime import datetime
from decimal import Decimal

import openpyxl

from .schedule import DATA_DIR

PRICE_FILE = os.path.join(DATA_DIR, 'price_table.json')
CONFIRMED_FILE = os.path.join(DATA_DIR, 'price_confirmed.json')

# xlsx 列按表头名识别，兼容两种格式：
# 《生产货号货价浏览总表》（货号编码/货价日期/总货号/产品货号/客户/外箱-装箱数/货币/客货价/客货价(HK$)/货运类别）
# 《华康B生产货号货价》（多了 货号摘要、长货号 两列，顺序不同）
HEADER_MAP = {
    '货号编码': 'code', '货价日期': 'date', '总货号': 'total_item',
    '产品货号': 'item', '客户': 'customer', '外箱-装箱数': 'carton_qty',
    '货币': 'currency', '客货价': 'price', '客货价(HK$)': 'price_hk',
    '货运类别': 'category', '长货号': 'long_item',
}

FIELDS = ['code', 'date', 'total_item', 'item', 'customer', 'carton_qty',
          'currency', 'price', 'price_hk', 'category', 'long_item']

# 货价确认表（文员填好「确认价格」后喂回系统）的表头识别，
# 兼容系统导出的批次版（货号/邮件长货号/…）和全表版（产品货号/…）
CONFIRM_HEADER_MAP = {
    '货号': 'item', '产品货号': 'item', '邮件长货号': 'long_item',
    '货运类别': 'category', '装箱数': 'carton_qty',
    '货币': 'currency', '候选客货价': 'cand_price', '候选客货价(HK$)': 'cand_hk',
    '确认价格(文员填写)': 'confirmed', '确认价格': 'confirmed',
    '确认币种': 'confirmed_currency', '确认价格币种': 'confirmed_currency',
}

def _confirmed_amount(value):
    """Read an explicit amount, never the last unrelated number or guessed currency."""
    raw = str(value).strip().upper().replace(',', '')
    numeric = r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)'
    labels = list(re.finditer(r'HK\$|HKD|港币|港幣|US\$|USD|美金|美元', raw))
    if not labels:
        if not re.fullmatch(numeric, raw):
            raise ValueError('确认价格必须是数字或明确的 HK$/US$ 金额')
        return Decimal(raw), ''
    if len(labels) != 1:
        raise ValueError('确认价格包含多个币种或金额标签，请拆成单一金额')
    label = labels[0]
    currency = 'HKD' if label.group() in ('HK$', 'HKD', '港币', '港幣') else 'USD'
    after = re.match(r'\s*(' + numeric + r')(?![\d.])', raw[label.end():])
    if after:
        # A second unlabelled amount/revision is not a quantity annotation.
        # Preserve explicit "qty1000" and per-piece units, never pick the first
        # price from "US$2.90 or 3.50" / "revised to 3.50".
        tail = raw[label.end() + after.end():]
        prefix = raw[:label.start()].strip()
        allowed = r'\s*(?:/\s*(?:PCS?|EACH))?(?:\s*[,;]?\s*QTY\s*[:=]?\s*\d+(?:\s*PCS?)?)?\s*'
        if (not re.fullmatch(allowed, tail) or re.search(r'\b(?:OR|REVISED|FROM|TO|WAS|NOW)\b', prefix)
                or (re.search(r'\d', prefix) and not re.fullmatch(r'\d{5}(?:\([A-Z0-9 _-]+\))?', prefix))):
            raise ValueError('确认价格包含其他金额或修订说明，请核对后只填写一个明确金额')
        return Decimal(after.group(1)), currency
    # Also allow an unambiguous "2.9 USD", but not a product code or trailing qty.
    before = raw[:label.start()].strip()
    if not raw[label.end():].strip() and re.fullmatch(numeric, before):
        return Decimal(before), currency
    raise ValueError('确认价格未找到紧邻币种的金额，请整理后再上传')



def _fmt_num(v):
    """数字尽量收成简洁字符串：33.930 -> 33.93；26.0 -> 26。"""
    if v in (None, ''):
        return ''
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v).strip()
    s = ('%f' % f).rstrip('0').rstrip('.')
    return s


def _fmt_date(v):
    if isinstance(v, datetime):
        return v.strftime('%Y-%m-%d')
    return str(v or '').strip()[:10]


def _base_item(s):
    """货号去后缀：93018-WB0 → 93018；89786-OPP → 89786。"""
    return str(s or '').strip().split('-')[0].strip()


def _norm_ctn(v):
    """装箱数归一化：4 / '4' / '4.0' 都视为 '4'。"""
    try:
        return str(int(float(str(v).strip())))
    except (ValueError, TypeError):
        return str(v or '').strip()


class PriceTable:
    def __init__(self):
        self.loaded = False
        self.name = ''
        self.uploaded_at = ''
        self.source_mtime = 0    # 来源文件的修改时间（自动更新据此判断是否有新版）
        self.records = []      # list[dict]，含 id
        self._next_id = 1
        # 文员确认价：key '货号|类别|装箱数' → {price, source, at}；
        # confirmed_long：key '长货号|类别' → 同上（更精确，优先用）
        self.confirmed = {}
        self.confirmed_long = {}
        self.confirmed_mtime = 0   # 已导入确认表来源文件的最新 mtime

    # ── 持久化 ─────────────────────────────
    def save(self):
        # References are immutable/versioned by Nexus, never desktop JSON files.
        return None

    def load_saved(self):
        # References are immutable/versioned by Nexus, never desktop JSON files.
        return None

    # ── 文员确认价（货价确认表回填）─────────────
    def save_confirmed(self):
        # References are immutable/versioned by Nexus, never desktop JSON files.
        return None

    def load_confirmed(self):
        # References are immutable/versioned by Nexus, never desktop JSON files.
        return None

    def import_confirmed_xlsx(self, path, name='', source_mtime=None, default_currency=None):
        """导入文员填好的货价确认表：只收「确认价格」列已填的行。
        返回 (填入行数, 跳过行数)。同 key 后导入的覆盖先导入的。"""
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        if ws.max_row and ws.max_row > 200000:
            wb.close()
            raise ValueError("货价参照超过 20 万行，请先整理")
        rows = ws.iter_rows(max_col=100, values_only=True)
        header = next(rows, None)
        col_of = {}
        for i, h in enumerate(header or []):
            key = CONFIRM_HEADER_MAP.get(str(h or '').strip())
            if key and key not in col_of:
                col_of[key] = i
        if 'confirmed' not in col_of or 'item' not in col_of:
            wb.close()
            raise ValueError('表头不对——请上传系统导出的《货价确认表》（需含「确认价格(文员填写)」列）')

        def cell(row, key):
            i = col_of.get(key)
            return row[i] if i is not None and i < len(row) else None

        at = datetime.now().strftime('%Y/%m/%d %H:%M')
        filled = skipped = 0
        for index, row in enumerate(rows, start=2):
            if index > 200000:
                wb.close()
                raise ValueError("确认价参照超过 20 万行，请先整理")
            if not row or all(c in (None, '') for c in row):
                continue
            raw_conf = cell(row, 'confirmed')
            item = str(cell(row, 'item') or '').strip()
            if raw_conf is None or str(raw_conf).strip() == '' or not item:
                continue
            try:
                amount, tagged = _confirmed_amount(raw_conf)
            except ValueError as exc:
                wb.close()
                raise ValueError(f'确认表第 {index} 行：{exc}') from exc
            # 确认价归一成港币：文员习惯填美金价，直接存会当成 HK$ 用（差 7.8 倍）
            explicit = str(cell(row, 'confirmed_currency') or '').strip().upper()
            if explicit and tagged and explicit != tagged:
                wb.close()
                raise ValueError(f"确认表第 {index} 行的币种与金额标签矛盾")
            cur = explicit or tagged or default_currency
            if cur not in ('HKD', 'USD'):
                wb.close()
                raise ValueError(f"确认表第 {index} 行未明确币种，请填确认币种 HKD/USD 或在上传时指定数字币种")
            conf_hkd = amount * Decimal('7.8') if cur == 'USD' else amount
            conf = format(conf_hkd, 'f')
            if '.' in conf:
                conf = conf.rstrip('0').rstrip('.')
            cat = str(cell(row, 'category') or '').strip()
            ctn = _norm_ctn(cell(row, 'carton_qty')) if cell(row, 'carton_qty') not in (None, '') else ''
            filled += 1
            val = {'price': conf, 'source': name, 'at': at}
            self.confirmed['|'.join([_base_item(item), cat, ctn])] = val
            lc = str(cell(row, 'long_item') or '').strip().upper()
            if lc:
                self.confirmed_long['|'.join([lc, cat])] = val
        wb.close()
        if source_mtime is None:
            try:
                source_mtime = os.path.getmtime(path)
            except OSError:
                source_mtime = 0
        self.confirmed_mtime = max(self.confirmed_mtime, source_mtime)
        self.save_confirmed()
        return filled, skipped

    def lookup_confirmed(self, item, category=None, carton=None, long_code=None):
        """查文员确认价：长货号+类别 优先，其次 货号+类别+装箱数（类别/装箱数可模糊）。"""
        lc = str(long_code or '').strip().upper()
        if lc:
            for cat in ([category, ''] if category else ['']):
                hit = self.confirmed_long.get('|'.join([lc, cat or '']))
                if hit:
                    return hit['price']
        base = _base_item(item)
        if not base or not self.confirmed:
            return ''
        ctn = _norm_ctn(carton) if carton not in (None, '') else ''
        best = None
        for key, v in self.confirmed.items():
            b, cat, c = key.split('|')
            if b != base:
                continue
            if category and cat and cat != category:
                continue
            if ctn and c and c != ctn:
                continue
            spec = (1 if category and cat == category else 0) \
                 + (1 if ctn and c == ctn else 0)
            if best is None or spec > best[0] \
                    or (spec == best[0] and v['at'] >= best[1]['at']):
                best = (spec, v)
        return best[1]['price'] if best else ''

    def confirmed_info(self):
        ats = [v['at'] for v in self.confirmed.values()]
        srcs = sorted({v['source'] for v in self.confirmed.values() if v['source']})
        return {'count': len(self.confirmed), 'long_count': len(self.confirmed_long),
                'sources': srcs, 'updated_at': max(ats) if ats else '',
                'confirmed_mtime': self.confirmed_mtime}

    # ── 导入 xlsx ──────────────────────────
    def import_xlsx(self, path, name='', source_mtime=None):
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        if ws.max_row and ws.max_row > 200000:
            wb.close()
            raise ValueError("货价参照超过 20 万行，请先整理")
        rows = ws.iter_rows(max_col=100, values_only=True)
        header = next(rows, None)
        if not header or '货价' not in ''.join(str(c or '') for c in header[:10]):
            wb.close()
            raise ValueError('表头不对——请上传《生产货号货价浏览总表》格式的货价表')
        col_of = {}
        for i, h in enumerate(header):
            key = HEADER_MAP.get(str(h or '').strip())
            if key and key not in col_of:
                col_of[key] = i
        missing = [k for k in ('code', 'item', 'price_hk', 'category') if k not in col_of]
        if missing:
            wb.close()
            raise ValueError('货价表缺少必需列：' + '、'.join(missing))

        def cell(row, key):
            i = col_of.get(key)
            return row[i] if i is not None and i < len(row) else None

        recs = []
        for index, row in enumerate(rows, start=2):
            if index > 200000:
                wb.close()
                raise ValueError("货价参照超过 20 万行，请先整理")
            if not row or not row[0]:
                continue
            item = str(cell(row, 'item') or '').strip()
            if not item:
                continue
            recs.append({
                'code': str(cell(row, 'code') or '').strip(),
                'date': _fmt_date(cell(row, 'date')),
                'total_item': str(cell(row, 'total_item') or '').strip(),
                'item': item,
                'customer': str(cell(row, 'customer') or '').strip(),
                'carton_qty': _fmt_num(cell(row, 'carton_qty')),
                'currency': str(cell(row, 'currency') or '').strip(),
                'price': _fmt_num(cell(row, 'price')),
                'price_hk': _fmt_num(cell(row, 'price_hk')),
                'category': str(cell(row, 'category') or '').strip(),
                'long_item': str(cell(row, 'long_item') or '').strip().upper(),
            })
        wb.close()
        if not recs:
            raise ValueError('没有读到任何货价记录')
        self.records = []
        self._next_id = 1
        for r in recs:
            r['id'] = self._next_id
            self._next_id += 1
            self.records.append(r)
        self.name = name
        self.uploaded_at = datetime.now().strftime('%Y/%m/%d %H:%M')
        if source_mtime is None:
            try:
                source_mtime = os.path.getmtime(path)
            except OSError:
                source_mtime = 0
        self.source_mtime = source_mtime
        self.loaded = True
        self.save()

    # ── 增删改查 ───────────────────────────
    def add(self, rec):
        rec = {k: str(rec.get(k, '')).strip() for k in FIELDS}
        if not rec['item']:
            raise ValueError('产品货号不能为空')
        rec['id'] = self._next_id
        self._next_id += 1
        self.records.append(rec)
        self.loaded = True
        self.save()
        return rec

    def update(self, rid, rec):
        for r in self.records:
            if r['id'] == rid:
                for k in FIELDS:
                    if k in rec:
                        r[k] = str(rec[k]).strip()
                if not r['item']:
                    raise ValueError('产品货号不能为空')
                self.save()
                return r
        raise ValueError('记录不存在')

    def delete(self, rid):
        before = len(self.records)
        self.records = [r for r in self.records if r['id'] != rid]
        if len(self.records) == before:
            raise ValueError('记录不存在')
        self.save()

    def search(self, q='', offset=0, limit=50):
        q = (q or '').strip().lower()
        rows = self.records
        if q:
            rows = [r for r in rows
                    if q in r['item'].lower() or q in r['customer'].lower()
                    or q in r['code'].lower() or q in r['total_item'].lower()]
        total = len(rows)
        return total, rows[offset:offset + limit]

    # ── 取价 ───────────────────────────────
    def lookup(self, item, category=None, carton=None):
        """按 货号(去后缀)+类别+装箱数 取价，并说明兜底情况：
        类别没有时退回全部类别（cat_fallback）；该装箱数没有时退回全部装箱数
        （carton_fallback）；最后取货价日期最新的一条。"""
        item = _base_item(item)
        res = {'price': '', 'found': False, 'cat_fallback': False,
               'carton_fallback': False, 'record': None}
        if not item:
            return res
        cands = [r for r in self.records if r['price_hk']
                 and (_base_item(r['item']) == item
                      or _base_item(r['total_item']) == item)]
        if not cands:
            return res
        if category:
            cat = [r for r in cands if r['category'] == category]
            if cat:
                cands = cat
            else:
                res['cat_fallback'] = True
        if carton:
            ctn = [r for r in cands
                   if _norm_ctn(r['carton_qty']) == _norm_ctn(carton)]
            if ctn:
                cands = ctn
            else:
                res['carton_fallback'] = True
        cands.sort(key=lambda r: (r['date'], r.get('id', 0)))
        res['price'] = cands[-1]['price_hk']
        res['found'] = True
        res['record'] = cands[-1]
        return res

    def has_long(self):
        """货价数据里是否带长货号（《华康B生产货号货价》格式才有）。"""
        return any(r.get('long_item') for r in self.records)

    def lookup_long(self, long_code, category=None):
        """按 长货号(+类别) 精确取价，取货价日期最新的一条。"""
        res = {'price': '', 'found': False, 'record': None}
        lc = str(long_code or '').strip().upper()
        if not lc:
            return res
        cands = [r for r in self.records
                 if r.get('long_item') == lc and r['price_hk']]
        if category:
            cands = [r for r in cands if r['category'] == category]
        if not cands:
            return res
        cands.sort(key=lambda r: (r['date'], r.get('id', 0)))
        res['price'] = cands[-1]['price_hk']
        res['found'] = True
        res['record'] = cands[-1]
        return res

    def latest_price(self, item, category=None, carton=None):
        return self.lookup(item, category, carton)['price']

    def info(self):
        age_days = None
        try:
            age_days = (datetime.now()
                        - datetime.strptime(self.uploaded_at, '%Y/%m/%d %H:%M')).days
        except Exception:
            pass
        return {'loaded': self.loaded, 'name': self.name,
                'uploaded_at': self.uploaded_at, 'count': len(self.records),
                'items': len({r['item'] for r in self.records}),
                'age_days': age_days,
                'source_mtime': self.source_mtime,
                'source_date': (datetime.fromtimestamp(self.source_mtime)
                                .strftime('%Y/%m/%d %H:%M') if self.source_mtime else ''),
                'confirmed': self.confirmed_info()}

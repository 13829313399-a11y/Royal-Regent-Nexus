"""Legacy factory-owned enrichment; reference objects are request-local."""
import re
from .parser import norm_carton

AMAZON_RE = re.compile(r'\bamazon|亚马逊', re.I)


def _price_category(customer):
    return '客派车' if AMAZON_RE.search(str(customer or '')) else '柜货'


def _case_pack_of(long_code):
    parts = str(long_code or '').strip().split('-')
    return str(int(parts[3])) if len(parts) >= 4 and parts[3].isdigit() else ''


def annotate(result, schedule_ref, price_table):
    """生成 T 列内容（货号T/子货号T/产品名称T/装箱数T）；有排期参照时同时做查重、国家/版本带出。"""
    n_exists = 0
    for o in result['orders']:
        baby = str(o.get('baby_item') or '').strip()
        long_code = str(o.get('long_code') or '').strip()
        case_pack = _case_pack_of(long_code)
        detail = schedule_ref.get_item_detail(baby) if schedule_ref.loaded else None
        if detail:
            # 排期表里有这个货号的资料，直接带出；装箱数以本单长货号为准（不同包装版本装箱数不同）
            o['item_t'] = detail.get('货号') or baby
            o['sub_item_t'] = detail.get('子货号') or ''
            o['product_t'] = detail.get('产品名称') or ''
            carton_raw = case_pack or detail.get('装箱数') or ''
        else:
            # 新货号：按排期表「货号 名称」「货号 后缀」的格式用邮件内容拼
            o['item_t'] = baby
            suffix = long_code.split('-')[-1] if long_code else ''
            o['sub_item_t'] = (baby + ' ' + suffix).strip()
            desc = str(o.get('description') or '').strip()
            o['product_t'] = (baby + ' ' + desc).strip()
            carton_raw = case_pack
        # 装箱数必须是整数：数量除不尽（如 1004/3）产生的小数取整并提示人工核对
        carton_norm, carton_rounded = norm_carton(carton_raw)
        o['carton_t'] = carton_norm
        if carton_rounded:
            result['warnings'].append(
                f'货号 {baby} 装箱数 {carton_raw} 不是整数（数量/箱数除不尽），'
                f'已取整为 {carton_norm}，请人工核对')
        # 货价：优先按 长货号+货运类别 精确匹配（货价表带长货号时）；
        # 其次用文员确认价（货价确认表回填）；
        # 都不行退回 货号+装箱数 取价，并标记「货价待确认」给文员出确认表
        # 货运类别按客户定：亚马逊系 → 客派车，其余 → 柜货
        if price_table.loaded:
            cat = _price_category(o.get('customer'))
            ctn = case_pack or o.get('carton_t') or ''
            long_hit = False
            conf_hit = ''
            cat_sub = False
            lg = {'price': '', 'found': False, 'cat_fallback': False,
                  'carton_fallback': False, 'record': None}
            if long_code and price_table.has_long():
                hit = price_table.lookup_long(long_code, cat)
                if hit['found']:
                    lg.update(price=hit['price'], found=True, record=hit['record'])
                    long_hit = True
                fhit = price_table.lookup_long(long_code, '出厂价')
                if fhit['found']:
                    o['factory_price_t'] = fhit['price']
            if not long_hit:
                conf_hit = price_table.lookup_confirmed(baby, cat, ctn, long_code)
                if conf_hit:
                    lg.update(price=conf_hit, found=True, record=None)
                else:
                    lg = price_table.lookup(baby, cat, ctn)
                    # 客派车没有时优先退回柜货价（客货价口径），避免同日期随机退到出厂价
                    if cat != '柜货' and lg['found'] and lg['cat_fallback']:
                        lg2 = price_table.lookup(baby, '柜货', ctn)
                        if lg2['found'] and not lg2['cat_fallback']:
                            lg, cat_sub = lg2, True
            if not o.get('factory_price_t'):
                o['factory_price_t'] = (
                    price_table.lookup_confirmed(baby, '出厂价', ctn, long_code)
                    or price_table.latest_price(baby, '出厂价', ctn))
            o['price_t'] = lg['price']
            o['price_missing'] = not lg['found']
            if cat == '柜货':
                # 柜货沿用文员口径：长货号未精确命中即待确认
                o['price_confirm'] = (price_table.has_long() and not long_hit
                                      and not conf_hit)
            else:
                # 客派车价在长货号表里稀少，按货号拿到对应类别价即算有效；
                # 只有完全没拿到该类别价（退回其他类别）才待确认
                o['price_confirm'] = (price_table.has_long() and not long_hit
                                      and not conf_hit
                                      and (not lg['found'] or lg['cat_fallback']))
            notes = []
            if cat != '柜货':
                notes.append('亚马逊订单按客派车取价')
            if conf_hit:
                notes.append('货价文员已确认')
            elif o['price_confirm'] and lg['found']:
                notes.append('长货号未匹配到货价，暂按货号+装箱数取价，待文员确认')
            if cat_sub:
                notes.append('无%s价，按柜货取价' % cat)
            elif lg['found'] and lg['cat_fallback']:
                notes.append('无%s价，按%s取价'
                             % (cat, (lg['record'] or {}).get('category', '其他')))
            if lg['found'] and lg['carton_fallback'] and ctn:
                notes.append('无箱%s价，按箱%s取价'
                             % (ctn, (lg['record'] or {}).get('carton_qty', '?')))
            o['price_note'] = '；'.join(notes)
            o['total_value'] = ''  # Commercial totals are not supplied to Kintable.
        else:
            o['price_t'] = o['factory_price_t'] = o['total_value'] = ''
            o['price_missing'] = True
            o['price_confirm'] = False
            o['price_note'] = ''
        if not schedule_ref.loaded:
            continue
        exists, known, suggest, version = schedule_ref.check_row(
            o.get('customer'), o.get('customer_po'), o.get('baby_item'), o.get('qty'))
        o['exists'] = exists
        o['known_item'] = known
        o['country_ref'] = suggest
        if not o.get('country') and suggest:
            o['country'] = suggest
        if version:
            cur_pkg = str(o.get('pkg') or '').strip()
            if not cur_pkg:
                o['pkg'] = version
                o['pkg_from_ref'] = True
            elif cur_pkg.upper() != version.upper():
                if o.get('quoted_original'):
                    result['warnings'].append(
                        f'货号 {baby} 最新回复包装 {cur_pkg} 与排期历史 {version} 不同，保留最新回复，请人工核对')
                else:
                    # Preserve the established current-table/history mapping;
                    # explicit quoted-reply updates above are a separate case.
                    result['warnings'].append(
                        f'货号 {baby} 版本按排期表历史映射：客人表格 {cur_pkg} → {version}，请确认')
                    o['pkg'] = version
                    o['pkg_from_ref'] = True
        if exists:
            n_exists += 1
    if n_exists:
        result['warnings'].append(
            f'该邮件有 {n_exists} 行在排期表中已存在（同客PO+货号 或 同客名+货号+数量），'
            f'可能已录入过，生成时默认排除；若这是该问单的确认单/正单，'
            f'请到金山把原问单直接转为确认单/正单，切勿重复录入')

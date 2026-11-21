"""Deterministic shipping-field rules with an auditable rule trace."""
import re
from dataclasses import dataclass, field

from app.services.shipping_schedule import parse_schedule_date, resolve_planned_ship_date

PORTS = {
    'YANTIAN': '盐田', 'YICT': '盐田', '盐田': '盐田',
    'SHEKOU': '蛇口', '蛇口': '蛇口',
    'NANSHA': '南沙', '南沙': '南沙',
    'HUANGPU': '黄埔', '黄埔': '黄埔',
    'CHIWAN': '赤湾', '赤湾': '赤湾',
    'SHANGHAI': '上海', 'NINGBO': '宁波', 'QINGDAO': '青岛', 'XIAMEN': '厦门',
}
COUNTRY_HINTS = (
    (('UNITED STATES', 'U.S.A', 'USA', 'US', 'TEXAS', 'CALIFORNIA', 'HOUSTON', 'LOS ANGELES'), '美国'),
    (('CANADA', 'TORONTO', 'VANCOUVER'), '加拿大'),
    (('FRANCE', 'LE HAVRE', 'MARSEILLE'), '法国'),
    (('UNITED KINGDOM', 'UK', 'ENGLAND', 'LONDON', 'FELIXSTOWE'), '英国'),
    (('GERMANY', 'HAMBURG', 'BREMERHAVEN'), '德国'),
    (('NETHERLANDS', 'ROTTERDAM'), '荷兰'),
    (('AUSTRALIA', 'SYDNEY', 'MELBOURNE'), '澳大利亚'),
    (('INDONESIA', 'JAKARTA', 'SURABAYA'), '印度尼西亚'),
    (('PHILIPPINES', 'MANILA'), '菲律宾'),
    (('VIETNAM', 'HO CHI MINH', 'HAI PHONG'), '越南'),
    (('MALAYSIA', 'PORT KLANG', 'PENANG'), '马来西亚'),
    (('SINGAPORE',), '新加坡'),
    (('THAILAND', 'BANGKOK', 'LAEM CHABANG'), '泰国'),
    (('SOUTH KOREA', 'KOREA', 'BUSAN'), '韩国'),
    (('TAIWAN', 'KAOHSIUNG', 'KEELUNG'), '中国台湾'),
    (('UNITED ARAB EMIRATES', 'UAE', 'DUBAI', 'JEBEL ALI'), '阿联酋'),
    (('SAUDI ARABIA', 'JEDDAH', 'RIYADH'), '沙特阿拉伯'),
    (('MEXICO', 'MANZANILLO', 'VERACRUZ'), '墨西哥'),
    (('BRAZIL', 'SANTOS'), '巴西'),
    (('CHILE', 'SAN ANTONIO'), '智利'),
    (('SOUTH AFRICA', 'DURBAN', 'CAPE TOWN'), '南非'),
    (('JAPAN', 'TOKYO', 'OSAKA'), '日本'),
)

_SI_LABELS = (
    re.compile(r'SI\s*CUT\s*(?:OFF|OFF\s*TIME)?', re.I),
    re.compile(r'S\s*[/\\.]\s*I\s*(?:CUT|CLOSING|DEADLINE)', re.I),
    re.compile(r'截\s*补\s*料\s*(?:时间|日期)?', re.I),
    re.compile(r'SI\s*截\s*止', re.I),
    re.compile(r'Shipping\s+instruction\s+closing', re.I),
    re.compile(r'SI\s+General\s+Cut-?\s*off', re.I),
    re.compile(r'INTENDED\s+SHIPPING\s+INSTRUCTION\s+CUT-?\s*OFF', re.I),
    re.compile(r'截止单证', re.I),
    re.compile(r'交重截数时间', re.I),
    re.compile(r'截数时间', re.I),
    re.compile(r'Doc\s+Cut-?\s*off', re.I),
)
_CY_LABELS = (
    re.compile(r'CY\s*CUT\s*(?:OFF)?', re.I),
    re.compile(r'CY\s*CLOSING', re.I),
    re.compile(r'截\s*关\s*(?:时间|日期)?', re.I),
    re.compile(r'CY\s*截', re.I),
    re.compile(r'VGM\s*cut\s*off', re.I),
    re.compile(r'FCL\s+delivery\s+date', re.I),
    re.compile(r'FCL\s+CY\s+CUT-?\s*OFF', re.I),
    re.compile(r'Cargo\s+Cut-?\s*off', re.I),
    re.compile(r'VGM\s+Closing\s+Date', re.I),
    re.compile(r'INTENDED\s+FCL\s+CONTAINER\s+DELIVERY\s+CUT-?\s*OFF', re.I),
    re.compile(r'INTENDED\s+VGM\s+CUT-?\s*OFF', re.I),
    re.compile(r'交重截数时间', re.I),
    re.compile(r'Port\s+Cut-?\s*off\s+Date/Time', re.I),
    re.compile(r'Port\s+Cargo\s+Cut-?\s*off', re.I),
    re.compile(r'VGM\s+Cut-?\s*off', re.I),
    re.compile(r'Full\s+Return\s+CY\s+Cut-?\s*off', re.I),
)
_SO_PATTERNS = (
    re.compile(r'Bill\s+of\s+Lading\s*#\s*[::]\s*([A-Z0-9-]{5,})', re.I),
    re.compile(r'\bBN\b\s*[::#]?\s*([A-Z]{0,4}\d{6,})', re.I),
    re.compile(r'\bROSS\b\s*[::#]?\s*(\d{8,})', re.I),
    re.compile(r'Booking\s+reference\s*[::]\s*([A-Z0-9-]{5,})', re.I),
    re.compile(r'BKG\s+Ref\.?\s*No\s*[::]\s*([A-Z0-9-]{5,})', re.I),
    re.compile(r'Booking\s*(?:No|Number|#)\s*[:\s.]*\s*([A-Z0-9][A-Z0-9-]{5,})', re.I),
    re.compile(r'\bSO\s*[#::]\s*(?!SO\b)([A-Z0-9][A-Z0-9-]{5,})', re.I),
    re.compile(r'订舱号\s*[::\s]*([A-Z0-9]{6,})', re.I),
)
_CONTAINER = re.compile(r'(\d+)\s*[*xX×]\s*(20|40|42|45)\s*(HQ|GP|HC|OT|FR|RF)', re.I)
_TYPE_CONTAINER = re.compile(r'Type\s*[::]\s*((?:\d+\s*[*xX×]\s*)?(20|40|42|45)\s*(HQ|GP|HC|OT|FR|RF))', re.I)
_VESSEL = (
    re.compile(r'Vessel\s*(?:Name)?\s*[::]\s*([^\n]{2,60})', re.I),
    re.compile(r'船\s*名\s*[::\s]*([^\n]{2,40})'),
)
_DESTINATION = (
    re.compile(r'^\s*To\s*[::]\s*([^\n]{3,80})', re.I | re.M),
    re.compile(r'Destination\s*[::]\s*([^\n]{3,80})', re.I),
    re.compile(r'目的港\s*[::\s]*([^\n]{2,60})'),
)
_CUSTOMER = (
    re.compile(r'Customer\s*[::]\s*([^\n]{2,60})', re.I),
    re.compile(r'客户(?:名称)?\s*[::]\s*([^\n]{2,40})'),
)
_TRANSPORT = (
    re.compile(r'运输公司\s*[::]\s*([^\n]{2,50})'),
    re.compile(r'(?:拖车公司|车队|车行|运输行|物流公司)\s*[::]\s*([^\n]{2,50})'),
    re.compile(r'(?:Trucker|Haulier|Transport(?:ation)?\s+Company|Trucking\s+Company)\s*[::]\s*([^\n]{2,50})', re.I),
)
_CONTRACT = (
    re.compile(r'Service\s+Contract\s*[::]\s*([A-Z0-9][A-Z0-9/\-]{2,40})', re.I),
    re.compile(r'Quotation\s*/\s*Contract\s*No\.?\s*[::]?\s*[\s\S]{0,240}?\b(\d{8,})\b', re.I),
    re.compile(r'Contract\s*(?:No\.?|Number|#)\s*[::.#]?\s*([A-Z0-9][A-Z0-9/\-]{2,40})', re.I),
    re.compile(r'合\s*同\s*(?:编)?\s*号\s*[::\s]*([A-Z0-9][A-Z0-9/\- ]{2,60})', re.I),
)
_WAREHOUSE = (
    re.compile(r'入\s*[盐蛇]?\s*港?\s*(\d{1,3})\s*号仓'),
    re.compile(r'仓库号\s*[::]?\s*(\d{1,3})'),
    re.compile(r'\b(\d{1,3})\s*号仓'),
)
_BOOKING_VESSEL = re.compile(r'([A-Z][A-Z]+(?:\s+[A-Z][A-Z]+){1,3})\s+(\d{2}-[A-Z]{3}-\d{4})')
_BOOKING_TYPES = re.compile(r'(\d+)\s*[*xX×]\s*(20|40|42|45)\s*(HQ|GP|HC|OT|FR|RF)', re.I)
_BOOKING_VOYAGE = re.compile(r'Voy\.?\s*No\.?\s*[::]\s*([A-Z0-9]+)', re.I)
_MAERSK_CONTRACT = re.compile(r'Service\s+Contract\s*[::]?\s*[\s\S]{0,200}?\b(\d{8,})\b', re.I)
_MAERSK_VESSEL = re.compile(r'\bMVS\s+([A-Z][A-Z ]{3,40}?)\s+(\d{3}[A-Z])\b')
_MAERSK_CONTAINER = re.compile(r'^\s*(\d{1,2})\s+(DRY|GP|HQ|HC|RF|OT|FR)\s*$', re.M)
_MAERSK_FROM = re.compile(r'^From:\s*\n([^\n]+)', re.M)
_MAERSK_TO = re.compile(r'^To:\s*\n([^\n]+)', re.M)
_MAERSK_ETD = re.compile(r'\b(\d{4}-\d{2}-\d{2})\s*$', re.M)
_BOOKING_DATE = (
    re.compile(r'(?:Booking|Booked)\s*Date\s*[::]\s*([^\n]{4,30})', re.I),
    re.compile(r'订\s*(?:舱|仓)\s*日\s*期\s*[::\s]*([^\n]{4,30})', re.I),
)
_VOYAGE = (
    re.compile(r'(?:Voyage|Voy\.?|VOY)\s*(?:No\.?)?\s*[::#]?\s*([A-Z0-9][A-Z0-9\-]{1,20})', re.I),
    re.compile(r'航\s*次\s*(?:号)?\s*[::\s]*([A-Z0-9][A-Z0-9\-]{1,20})', re.I),
)
_TERMINAL = (
    re.compile(r'Terminal\s*[::]\s*([^\n]{2,40})', re.I),
    re.compile(r'码\s*头\s*[::\s]*([^\n]{2,40})'),
)
_ROUTE = re.compile(r'\bFROM\s+([A-Z][A-Z .]{2,24}?)\s+TO\s+([A-Z][A-Z .]{2,24})', re.I)
_FROM_LINE = (
    re.compile(r'^\s*From\s*[::]\s*([^\n]{2,60})', re.I | re.M),
    re.compile(r'起\s*运\s*港\s*[::\s]*([^\n]{2,40})'),
)
_TO_LINE = (
    re.compile(r'^\s*To\s*[::]\s*([^\n]{2,60})', re.I | re.M),
    re.compile(r'目\s*的\s*港\s*[::\s]*([^\n]{2,40})'),
)
_TERMINAL_CODES = {
    'YICT': '盐田国际码头',
    'NSCT': '南沙海港码头',
    'GOCT': '南沙港务码头',
    'SCT': '蛇口集装箱码头',
    'CCT': '赤湾集装箱码头',
}

_ONE_VESSEL = re.compile(r'Vessel\s+Voy\s*age\s+Di\s*r\s*[::]\s*([A-Z][A-Z .]{2,35}?)\s+(\d{3}[A-Z])', re.I)
_ONE_LOADING = re.compile(r'P\s*o\s*rt\s+of\s+L\s*oading\s*[::]\s*([^\n]+)', re.I)
_ONE_DISCHARGE = re.compile(r'P\s*o\s*rt\s+of\s+D\s*is\s*ch\s*ar\s*ge\s*[::]\s*([^\n]+)', re.I)
_ONE_RATE = re.compile(r'Rate\s+Agreement\s+No\.?\s*[::]\s*([A-Z0-9]+?)(?=Port|\s|$)', re.I)
_ONE_TERMINAL = re.compile(r'Termin\s*al\s*[::]\s*(YICT|SCT|CCT|NSCT|GOCT)\b', re.I)

_ZIM_CONTAINER = re.compile(r'(\d+)\s*[xX×]\s*(HQ|GP|HC|OT|FR|RF|DRY)[\s-]*(\d{2})', re.I)
_ZIM_VESSEL = re.compile(r'Vessel\s+Code\s*:\s*([A-Z][A-Z0-9 .-]{2,30}?)\s+(\d{2,3}[A-Z]?)\s*Vessel/Voyage', re.I)

PARSER_VERSION = '2026-11-16.p7'

_COMMON_CONTRACT = (
    re.compile(r'RATE\s+AGREEMENT\s+REFERENCE\s*[::]\s*([A-Z0-9][A-Z0-9\-/]{3,40})', re.I),
    re.compile(r'Rate\s+Agreement\s+No\.?\s*[::]\s*([A-Z0-9][A-Z0-9\-/]{3,40})', re.I),
    re.compile(r'Contract\s+No\s*\(SQ/SC\)\s*[::]\s*([A-Z0-9][A-Z0-9\-/]{3,40})', re.I),
    re.compile(r'\bS/C\s*[::]\s*([A-Z0-9][A-Z0-9\-/]{3,40})', re.I),
    re.compile(r'服务合同号\s*/\s*运价协议号\s*[::]\s*([A-Z0-9][A-Z0-9\-/]{3,40})'),
    re.compile(r'Service\s+Contract\s+no\.?\s*[\\\s]*VIP\s+Code\s*[::]\s*([A-Z0-9][A-Z0-9\-/]{3,40})', re.I),
)
_COMMON_LOADING = (
    re.compile(r'Port\s+of\s+Loading\s*[::]\s*([^\n]+)', re.I),
    re.compile(r'装货港\s*[::]\s*([^\n;]+)'),
    re.compile(r'装港(?:\(挂靠码头\))?\s*[::]\s*([^\n(]+)'),
    re.compile(r'\bPOR\s*[::]\s*([^\n]+)', re.I),
)
_COMMON_DISCHARGE = (
    re.compile(r'Port\s+of\s+Discharg\w*\s*[::]\s*([^\n]+)', re.I),
    re.compile(r'卸货港\s*[::]\s*([^\n;]+)'),
    re.compile(r'卸港\s*[::]\s*([^\n/]+)'),
    re.compile(r'PORT\s+OF\s+DISCHARGE\s*[::]\s*([^\n]+)', re.I),
)
_COMMON_VESSEL = (
    re.compile(r'(?:1st\s+)?Vessel\s*/\s*Voyage\s*[::]\s*([^\n]+)', re.I),
    re.compile(r'船名\s*/\s*航次\s*[::]\s*([^\n]+)'),
    re.compile(r'INTENDED\s+VESSEL\s*/\s*VOYAGE\s*[::]\s*([^\n]+)', re.I),
    re.compile(r'VESSEL\s*/\s*VOYAGE\s*[::]\s*([^\n]+)', re.I),
    re.compile(r'Vessel\s+Voyage(?:\s+Dir)?\s*[::]\s*([^\n]+)', re.I),
)
_COMMON_CONTAINER = (
    re.compile(r'(\d+)\s*[xX×]\s*(\d{2})\s*\'?\s*(HIGH\s+CUBE|HI-?\s*CUBE|HC|HQ|DRY\s+VAN|DRY|GP)', re.I),
    re.compile(r'(\d+)\s*[xX×]\s*HC\s*(\d{2})', re.I),
    re.compile(r'(\d{2})\s*\'\s*(HIGH\s+CUBE|HI-?\s*CUBE|DRY\s+VAN|DRY)', re.I),
    re.compile(r'Equipment\s+Size\s*[::]\s*(4H)', re.I),
)


@dataclass
class FieldExtraction:
    fields: dict = field(default_factory=dict)
    trace: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _apply_zim_booking(text: str, result: FieldExtraction) -> None:
    vessel = _ZIM_VESSEL.search(text)
    if not vessel:
        return
    result.fields['vessel_name'] = _clean(vessel.group(1))
    result.fields['voyage_no'] = vessel.group(2)
    if 'YANTIAN' in text.upper():
        result.fields['terminal'] = '盐田国际码头'


def _apply_one_booking(text: str, result: FieldExtraction) -> None:
    fields = result.fields
    vessel = _ONE_VESSEL.search(text)
    if vessel:
        fields['vessel_name'] = _clean(vessel.group(1))
        fields['voyage_no'] = vessel.group(2)
    loading = _ONE_LOADING.search(text)
    if loading:
        value = _clean(loading.group(1)).split(',')[0].strip()
        fields['from_port'] = '盐田' if 'YANTIAN' in value.upper() else value
        fields['port'] = fields['from_port']
    discharge = _ONE_DISCHARGE.search(text)
    if discharge:
        value = _clean(discharge.group(1)).split(',')[0].strip()
        fields['to_port'] = value
        fields['destination'] = value
        fields['destination_country'] = _country(value) or _country(text)
    rate = _ONE_RATE.search(text)
    if rate:
        fields['contract_no'] = rate.group(1).strip()
        fields['contract_tails'] = _contract_tails(fields['contract_no'])
    terminal = _ONE_TERMINAL.search(text)
    if terminal:
        code = terminal.group(1).upper()
        fields['terminal'] = _TERMINAL_CODES.get(code, code)


def extract_fields(text: str, *, received_at: str = '') -> FieldExtraction:
    result = FieldExtraction()
    year = _year_hint(text, received_at)
    so = _first_group(text, _SO_PATTERNS)
    result.fields['so_number'] = so
    result.fields['booking_no'] = so
    result.trace.append(_trace('SHIP-SO-001', {'so_number': so, 'booking_no': so}))
    if not so:
        result.warnings.append('未识别到 SO/BN 订舱号，需人工确认')

    container = _CONTAINER.search(text)
    container_type = f'{container.group(1)}*{container.group(2)}{container.group(3).upper()}' if container else ''
    if not container_type:
        type_container = _TYPE_CONTAINER.search(text)
        if type_container:
            count = type_container.group(1).split('*')[0].strip() if '*' in type_container.group(1) else '1'
            container_type = f'{count}*{type_container.group(2)}{type_container.group(3).upper()}'
    if not container_type:
        zim = _ZIM_CONTAINER.search(text)
        if zim:
            kind = 'GP' if zim.group(2).upper() == 'DRY' else zim.group(2).upper()
            container_type = f'{zim.group(1)}*{zim.group(3)}{kind}'
    result.fields['container_type'] = container_type
    result.trace.append(_trace('SHIP-CT-001', {'container_type': container_type}))

    vessel_name = _first_group(text, _VESSEL)
    result.fields['vessel_name'] = vessel_name
    result.trace.append(_trace('SHIP-VESSEL-001', {'vessel_name': vessel_name}))

    si, si_candidates = _deadline(text, _SI_LABELS, year)
    result.fields['si_deadline'] = si
    result.trace.append(_trace('SHIP-SI-001', {'si_deadline': si, 'candidates': si_candidates}))
    if not si:
        result.warnings.append('未识别到 SI 截止时间，需人工补充')
    elif len(si_candidates) > 1:
        result.warnings.append(f'识别到多个 SI 截止时间（{("、".join(si_candidates))}），已采用最早时间，请人工确认')

    cutoff, cutoff_candidates = _deadline(text, _CY_LABELS, year)
    result.fields['cutoff_date'] = cutoff
    result.trace.append(_trace('SHIP-CY-001', {'cutoff_date': cutoff}))
    if not cutoff:
        result.warnings.append('未识别到截关时间，需人工补充')
    elif len(cutoff_candidates) > 1:
        result.warnings.append(f'识别到多个截关时间（{("、".join(cutoff_candidates))}），已采用最早时间，请人工确认')

    port = _port(text)
    result.fields['port'] = port
    result.trace.append(_trace('SHIP-PORT-001', {'port': port}))

    warehouse_no = _first_group(text, _WAREHOUSE)
    result.fields['warehouse_no'] = warehouse_no
    result.trace.append(_trace('SHIP-WH-001', {'warehouse_no': warehouse_no}))

    destination = _first_group(text, _DESTINATION)
    result.fields['destination'] = destination
    result.fields['destination_country'] = _country(destination or text)
    result.trace.append(_trace('SHIP-DEST-001', {
        'destination': destination, 'destination_country': result.fields['destination_country'],
    }))

    customer = _first_group(text, _CUSTOMER)
    result.fields['customer'] = customer
    result.trace.append(_trace('SHIP-CUST-001', {'customer': customer}))

    contract = _first_group(text, _CONTRACT)
    result.fields['contract_no'] = contract
    result.fields['contract_tails'] = _contract_tails(contract)
    transport = _first_group(text, _TRANSPORT)
    if transport:
        result.fields['transport_company'] = transport
    result.trace.append(_trace('SHIP-CON-001', {
        'contract_no': contract, 'contract_tails': result.fields['contract_tails'],
    }))

    route = _ROUTE.search(text)
    from_port = _clean(route.group(1)) if route else _clean(_first_group(text, _FROM_LINE))
    to_port = _clean(route.group(2)) if route else _clean(_first_group(text, _TO_LINE))
    result.fields['from_port'] = from_port
    result.fields['to_port'] = to_port or destination
    if not result.fields['destination_country']:
        result.fields['destination_country'] = _country(result.fields['to_port'] or text)
    result.trace.append(_trace('SHIP-ROUTE-001', {
        'from_port': from_port, 'to_port': result.fields['to_port'],
        'destination_country': result.fields['destination_country'],
    }))

    voyage = _first_group(text, _VOYAGE)
    result.fields['voyage_no'] = voyage
    result.trace.append(_trace('SHIP-VOY-001', {'voyage_no': voyage}))

    booking_date_raw = _first_group(text, _BOOKING_DATE)
    booking_date = parse_schedule_date(booking_date_raw, year) if booking_date_raw else None
    result.fields['booking_date'] = booking_date.isoformat() if booking_date else ''
    result.trace.append(_trace('SHIP-BDATE-001', {'booking_date': result.fields['booking_date']}))

    if re.search(r'Booking\s+Confirmation|HAPAG-LLOYD', text, re.I):
        _apply_booking_confirmation(text, result, year)
        port = result.fields.get('port') or port
        cutoff = result.fields.get('cutoff_date') or cutoff
        si = result.fields.get('si_deadline') or si
        container_type = result.fields.get('container_type') or container_type
    if re.search(r'\bMAERSK\b|BOOKING\s+AMENDMENT', text, re.I):
        _apply_maersk_booking(text, result, year)
        port = result.fields.get('port') or port
        cutoff = result.fields.get('cutoff_date') or cutoff
        si = result.fields.get('si_deadline') or si
        container_type = result.fields.get('container_type') or container_type
    _apply_common_labels(text, result)
    port = result.fields.get('port') or port
    cutoff = result.fields.get('cutoff_date') or cutoff
    si = result.fields.get('si_deadline') or si
    container_type = result.fields.get('container_type') or container_type

    terminal = _terminal(text, port)
    result.fields['terminal'] = terminal
    result.fields['table_name'] = f'{terminal or port or "待定码头"}SO排期表'
    result.trace.append(_trace('SHIP-TERM-001', {'terminal': terminal, 'table_name': result.fields['table_name']}))

    planned = resolve_planned_ship_date(
        ship_date=_ship_date_text(text),
        cutoff_date=cutoff,
        si_deadline=si,
        received_at=received_at,
    )
    result.fields['planned_ship_date'] = planned.isoformat() if planned else ''
    if result.fields.get('maersk_etd'):
        try:
            from datetime import date as _date
            result.fields['planned_ship_date'] = _date.fromisoformat(result.fields['maersk_etd']).isoformat()
        except ValueError:
            pass
    result.trace.append(_trace('SHIP-DATE-001', {'planned_ship_date': result.fields['planned_ship_date']}))
    if re.search(r'Booking\s+Receipt\s+Notice|Vessel\s+Voy\s*age', text, re.I):
        _apply_one_booking(text, result)
    if re.search(r'Vessel\s+Code\s*:|Shipping\s+Order\s+No\.', text, re.I):
        _apply_zim_booking(text, result)

    mode = 'warehouse' if re.search(r'交仓|入仓|散货收货站|\bCFS\b', text, re.I) else ('container' if container_type else 'unknown')
    result.fields['shipment_mode'] = mode
    result.trace.append(_trace('SHIP-MODE-001', {'shipment_mode': mode}))
    result.fields['parser_version'] = PARSER_VERSION
    for key in ('port', 'from_port'):
        value = str(result.fields.get(key) or '').strip()
        if 'FLAG:' in value.upper() or '码头' in value or re.match(r'^[A-Z]{4}\d', value):
            result.fields[key] = ''
    return result


def _apply_booking_confirmation(text: str, result: FieldExtraction, year: int) -> None:
    if 'CNYTN YANTIAN' in text.upper():
        result.fields['from_port'] = '盐田'
        result.fields['port'] = '盐田'
    """Override fields with the structured layout of carrier booking confirmations."""
    fields = result.fields
    contract = _first_group(text, (_CONTRACT[0],))
    if contract:
        fields['contract_no'] = contract
        fields['contract_tails'] = _contract_tails(contract)

    vessel_match = _BOOKING_VESSEL.search(text)
    if vessel_match:
        fields['vessel_name'] = _clean(vessel_match.group(1))
        parsed = parse_schedule_date(vessel_match.group(2), year)
        if parsed:
            fields['booking_date'] = parsed.isoformat()

    voyage = _first_group(text, (_BOOKING_VOYAGE,))
    if voyage:
        fields['voyage_no'] = voyage

    container_types: list[str] = []
    for count, size, kind in _BOOKING_TYPES.findall(text):
        value = f'{count}*{size}{kind.upper()}'
        if value not in container_types:
            container_types.append(value)
    if container_types:
        fields['container_type'] = ', '.join(container_types)

    from_match = re.search(r'\b(CN[A-Z]{3})\s+([A-Z][A-Z ]{2,30})', text)
    if from_match:
        fields['from_port'] = '盐田' if from_match.group(1) == 'CNYTN' else _clean(from_match.group(0))
        fields['port'] = fields['from_port']
    to_match = re.search(r'\b(DE[A-Z]{3})\s+([A-Z][A-Z ]{2,30})', text)
    if to_match:
        fields['to_port'] = _clean(to_match.group(0)).split(' DP ')[0].strip()
        fields['destination'] = fields['to_port']
        fields['destination_country'] = _country(to_match.group(2)) or _country(text)

    si, _ = _deadline(text, (re.compile(r'Shipping\s+instruction\s+closing', re.I),), year)
    if si:
        fields['si_deadline'] = si
    cutoff, _ = _deadline(text, (re.compile(r'VGM\s*cut\s*off', re.I), re.compile(r'FCL\s+delivery\s+date', re.I)), year)
    if cutoff:
        fields['cutoff_date'] = cutoff

    result.trace.append(_trace('SHIP-BOOKING-001', {
        'vessel_name': fields.get('vessel_name'), 'voyage_no': fields.get('voyage_no'),
        'container_type': fields.get('container_type'), 'contract_no': fields.get('contract_no'),
        'from_port': fields.get('from_port'), 'to_port': fields.get('to_port'),
        'cutoff_date': fields.get('cutoff_date'), 'si_deadline': fields.get('si_deadline'),
    }))


def _clean_port(value: str) -> str:
    text = re.split(r'\s+/\s+|\s+(?:ETA|ETD|TML|Facility|Terminal|Port\s+Cut-?|Port\s+Cargo|SI\s+Cut)\b|[,;]', _clean(value), maxsplit=1, flags=re.I)[0]
    return text.strip(' .:-')


def _parse_vessel_voyage(raw: str) -> tuple[str, str]:
    text = re.sub(r'\([^)]*\)', '', _clean(raw))
    text = re.split(r'\s+(?:ETD|ETA|ETB|Vessel\s+Code)\b', text, maxsplit=1, flags=re.I)[0]
    if '/' in text:
        left, right = text.rsplit('/', 1)
        if re.fullmatch(r'(?=[A-Z0-9]*\d)[A-Z0-9]{3,12}', right.strip()):
            return _clean(left), _clean(right)
    tokens = text.split()
    for index in range(len(tokens) - 1, -1, -1):
        if re.fullmatch(r'(?=[A-Z0-9]*\d)[A-Z0-9]{3,12}', tokens[index]):
            return ' '.join(tokens[:index]), tokens[index]
    return text, ''


def _apply_common_labels(text: str, result: FieldExtraction) -> None:
    """Fill fields from labels shared by HMM / MSC / OOCL / COSCO / ZIM layouts."""
    fields = result.fields

    contract = _first_group(text, _COMMON_CONTRACT)
    if contract and (not fields.get('contract_no') or not re.search(r'\d', fields['contract_no'])):
        fields['contract_no'] = contract
        fields['contract_tails'] = _contract_tails(contract)

    loading = _clean_port(_first_group(text, _COMMON_LOADING))
    if loading:
        fields['from_port'] = '盐田' if 'YANTIAN' in loading.upper() else loading
        fields['port'] = fields['from_port']

    discharge = _clean_port(_first_group(text, _COMMON_DISCHARGE))
    if discharge:
        fields['to_port'] = discharge
        fields['destination'] = discharge
        fields['destination_country'] = _country(discharge) or _country(text)

    vessel_raw = _first_group(text, _COMMON_VESSEL)
    if vessel_raw:
        name, voyage = _parse_vessel_voyage(vessel_raw)
        if name:
            fields['vessel_name'] = name
        if voyage:
            fields['voyage_no'] = voyage

    candidates: list[tuple[str, str, str]] = []
    for match in _COMMON_CONTAINER[0].finditer(text):
        candidates.append((match.group(1), match.group(2), match.group(3)))
    for match in _COMMON_CONTAINER[1].finditer(text):
        candidates.append((match.group(1), match.group(2), 'HC'))
    for match in _COMMON_CONTAINER[2].finditer(text):
        candidates.append(('1', match.group(1), match.group(2)))
    if _COMMON_CONTAINER[3].search(text):
        candidates.append(('1', '40', 'HC'))
    if candidates and ',' not in str(fields.get('container_type') or ''):
        chosen = next((item for item in candidates if 'HIGH' in item[2].upper() or item[2].upper() in ('HC', 'HQ')), candidates[0])
        count, size, kind = chosen
        normalized = 'HQ' if 'HIGH' in kind.upper() or 'HI-' in kind.upper() or kind.upper() in ('HC', 'HQ') else ('GP' if 'DRY' in kind.upper() else kind.upper())
        fields['container_type'] = f'{count}*{size}{normalized}'

    result.trace.append(_trace('SHIP-LABELS-001', {
        'contract_no': fields.get('contract_no'), 'from_port': fields.get('from_port'),
        'to_port': fields.get('to_port'), 'vessel_name': fields.get('vessel_name'),
        'voyage_no': fields.get('voyage_no'), 'container_type': fields.get('container_type'),
    }))


def _apply_maersk_booking(text: str, result: FieldExtraction, year: int) -> None:
    """Override fields for Maersk booking amendments / scanned booking PDFs."""
    fields = result.fields
    contract = _first_group(text, (_MAERSK_CONTRACT,))
    if contract and contract != fields.get('so_number'):
        fields['contract_no'] = contract
        fields['contract_tails'] = _contract_tails(contract)

    vessel = _MAERSK_VESSEL.search(text)
    if vessel:
        fields['vessel_name'] = _clean(vessel.group(1))
        fields['voyage_no'] = vessel.group(2)
        etd = _MAERSK_ETD.search(text[vessel.end():vessel.end() + 240])
        if etd:
            fields['maersk_etd'] = etd.group(1)

    container = _MAERSK_CONTAINER.search(text)
    if container:
        kind = 'GP' if container.group(2).upper() == 'DRY' else container.group(2).upper()
        fields['container_type'] = f'1*{container.group(1)}{kind}'

    origin_match = _MAERSK_FROM.search(text)
    if origin_match:
        origin = _clean(origin_match.group(1))
        fields['from_port'] = '盐田' if 'YANTIAN' in origin.upper() else origin
        fields['port'] = fields['from_port']
    destination_match = _MAERSK_TO.search(text)
    if destination_match:
        destination = _clean(destination_match.group(1))
        fields['to_port'] = destination
        fields['destination'] = destination
        fields['destination_country'] = _country(destination) or _country(text)

    result.trace.append(_trace('SHIP-MAERSK-001', {
        'so_number': fields.get('so_number'), 'contract_no': fields.get('contract_no'),
        'vessel_name': fields.get('vessel_name'), 'voyage_no': fields.get('voyage_no'),
        'container_type': fields.get('container_type'), 'from_port': fields.get('from_port'),
        'to_port': fields.get('to_port'), 'destination_country': fields.get('destination_country'),
        'maersk_etd': fields.get('maersk_etd'),
    }))


def _deadline(text: str, labels, year: int) -> tuple[str, list[str]]:
    candidates: list[str] = []
    for label in labels:
        for match in label.finditer(text):
            window = text[match.end():match.end() + 160]
            parsed = parse_schedule_date(window, year)
            if parsed is None:
                from datetime import date as _date
                fallback = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', window)
                if fallback:
                    try:
                        parsed = _date(int(fallback.group(3)), int(fallback.group(2)), int(fallback.group(1)))
                    except ValueError:
                        parsed = None
            if parsed is None:
                from datetime import date as _date
                months = {name: index for index, name in enumerate(
                    ('jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'), start=1)}
                compact = re.search(r'(\d{1,2})\s*([A-Za-z]{3})\s*(\d{2})\b', window)
                if compact and compact.group(2).lower() in months:
                    try:
                        parsed = _date(2000 + int(compact.group(3)), months[compact.group(2).lower()], int(compact.group(1)))
                    except ValueError:
                        parsed = None
            if parsed is None:
                continue
            clock = re.search(r'(\d{1,2})\s*[::]\s*(\d{2})', window[:80])
            hour, minute = (int(clock.group(1)), int(clock.group(2))) if clock else (0, 0)
            value = f'{parsed.isoformat()}T{hour:02d}:{minute:02d}'
            if value not in candidates:
                candidates.append(value)
    return (min(candidates) if candidates else ''), candidates


def _port(text: str) -> str:
    head = text[:4000].upper()
    for token, name in PORTS.items():
        if token.upper() in head:
            return name
    return ''


def _country(text: str) -> str:
    upper = (text or '').upper()
    for hints, name in COUNTRY_HINTS:
        for hint in hints:
            if re.search(rf'\b{re.escape(hint)}\b', upper):
                return name
    return ''


def _ship_date_text(text: str) -> str:
    match = re.search(
        r'(?:出货|走货|出运|提货)(?:日期|时间|日)?\s*[::]\s*'
        r'((?:20\d{2}[/.-])?\d{1,2}[/月.-]\d{1,2})',
        text,
    )
    return match.group(1) if match else ''


def _first_group(text: str, patterns) -> str:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return re.sub(r'\s+', ' ', match.group(1)).strip()
    return ''


def _clean(value: str) -> str:
    return re.sub(r'\s+', ' ', value or '').strip(' .:-')


def _contract_tails(contract: str) -> list[str]:
    """合同号后四位数列：CT-100/200/300 → ['100', '200', '300']；长合同号取末四位。"""
    if not contract:
        return []
    tails: list[str] = []
    for token in re.split(r'[/,\s]+', contract):
        digits = re.sub(r'\D', '', token)
        if not digits:
            continue
        tail = digits[-4:]
        if tail not in tails:
            tails.append(tail)
    return tails


def _terminal(text: str, port: str) -> str:
    upper = (text or '').upper()
    for code, name in _TERMINAL_CODES.items():
        if re.search(rf'\b{code}\b', upper):
            return name
    line = _first_group(text, _TERMINAL)
    if line:
        return line
    return f'{port}码头' if port else ''


def _year_hint(text: str, received_at: str) -> int:
    from datetime import date

    match = re.search(r'20\d{2}', received_at or '')
    if match:
        return int(match.group(0))
    match = re.search(r'\b(20\d{2})\b', text or '')
    return int(match.group(1)) if match else date.today().year


def _trace(rule_id: str, result: dict) -> dict:
    return {'rule_id': rule_id, 'result': result}

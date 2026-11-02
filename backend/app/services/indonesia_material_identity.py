"""Material names distinguish shared supplier codes; ledger IDs own stock identity."""
import json
import unicodedata


def value_key(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value or '')).strip().split()).casefold()


def catalog_identity(data):
    return tuple(value_key(data.get(field)) for field in ('code', 'name', 'specification'))


def shipment_material_key(line):
    supply = line.get('supply') or {}
    material_id = supply.get('material_id') or (supply.get('material_snapshot') or {}).get('id')
    if material_id:
        return material_id
    # Older externally-created snapshots may not carry the ledger ID.
    return 'legacy:' + json.dumps([str(line['material'].get(field) or '') for field in ('code', 'name', 'specification')], ensure_ascii=False)

"""Factory-scoped maintained choices; never infer people or agencies from free text."""
import json
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings

GROUPS = ('inspectors', 'institutions', 'hongKongContacts')


def choices(factory, actor=None):
    path = Path(settings.qc_department_data_dir) / 'options.json'
    try:
        raw = json.loads(path.read_text('utf-8')).get(factory, {}) if path.exists() else {}
        result = {}
        for group in GROUPS:
            items = raw.get(group, [])
            if not isinstance(items, list):
                raise ValueError('invalid options')
            result[group] = []
            seen = set()
            for item in items:
                if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                        or not isinstance(item.get('name'), str) or not item['id'].strip()
                        or not item['name'].strip() or len(item['id']) > 255 or len(item['name']) > 255
                        or item['id'] in seen):
                    raise ValueError('invalid choice')
                seen.add(item['id'])
                if item.get('active', True):
                    result[group].append(dict(id=item['id'], name=item['name']))
        # The current authenticated QC operator is a verified selectable identity.
        if actor and str(actor['id']) not in {x['id'] for x in result['inspectors']}:
            result['inspectors'].append(dict(id=str(actor['id']), name=actor['name']))
        return result
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise HTTPException(503, 'QC 选项配置无法读取，请联系管理员；原有填写内容不变') from exc


def selection(factory, actor, group, identity):
    if identity == '':
        return ''
    found = next((x for x in choices(factory, actor)[group] if x['id'] == identity), None)
    if not found:
        raise HTTPException(422, '所选人员或机构已不在本厂区有效选项中，请刷新选择')
    return found['name']

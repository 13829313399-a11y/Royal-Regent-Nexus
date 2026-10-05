"""Small deterministic manufacturing vocabulary, scoped to image documents."""
import re
from .document_ir import ToolError

TERMS = {
    'hair': '头发', 'hair gradation': '头发渐变', 'gradation': '渐变',
    'skin': '肤色', 'skin red': '肤色偏红', 'skin red tone': '肤色偏红', 'tone': '色调',
    'iris': '虹膜', 'iris bright': '虹膜高光', 'iris bright shade': '虹膜高光色', 'shade': '色调',
    'orange': '橙色', 'white': '白色', 'grey': '灰色', 'gray': '灰色',
    'purple': '紫色', 'black': '黑色', 'red': '红色', 'blue': '蓝色', 'green': '绿色',
    'fabric': '布料', 'orange fabric': '橙色布料', 'white fabric': '白色布料',
    'grey fabric': '灰色布料', 'purple fabric': '紫色布料', 'black fabric': '黑色布料',
    'shoe sole': '鞋底', 'tentacle': '触手', 'scale': '比例', 'deco': '配色图',
    'mini plush': '迷你毛绒玩具', 'plush': '毛绒玩具',
    'standing plush': '站立式毛绒玩具', 'plush guide': '毛绒玩具指南',
    'front': '正面', 'back': '背面', 'left': '左侧', 'right': '右侧',
    'top': '顶部', 'bottom': '底部',
    'front right': '右前方', 'front left': '左前方',
    'back right': '右后方', 'back left': '左后方',
    'quantity': '数量', 'quantity & description': '数量及说明', 'and up': '及以上',
    'safety & reliability specification': '安全与可靠性规格要求',
    'general description': '一般说明', 'product specification': '产品规格',
    'package specification': '包装规格', 'inspection criteria': '检验标准',
    'sampling plan': '抽样方案', 'classification of defects': '缺陷分类',
    'master carton': '外箱', 'defective score': '缺陷等级', 'package aesthetic': '包装外观',
    'product aesthetic': '产品外观', 'product functional': '产品功能',
    'critical': '致命', 'major': '主要', 'minor': '次要', 'safety': '安全',
    'per severity': '按严重程度', 'version no.': '版本号', 'control no.': '文件编号',
    'item no.': '产品编号', 'item name': '产品名称', 'asst. no.': '系列编号', 'asst. name': '系列名称',
    'drop test': '跌落测试', 'compression test': '压力测试', 'torque & tension test': '扭力与拉力测试',
    'humidity test': '湿度测试', 'aging test': '老化测试', 'adhesion test': '附着力测试',
    'abrasion test': '耐磨测试', 'hair pull test': '毛发拉力测试',
    'closed box': '封闭盒', 'window box': '开窗盒', 'blister card': '吸塑卡',
    'inner blister': '内吸塑', 'instruction sheet': '说明书', 'polybag': '胶袋',
    'clamshell': '对折吸塑', 'flip panel': '翻盖', 'open window box': '开放式开窗盒',
    'display tray': '展示托盘', 'hand tag': '吊牌', 'booklet': '手册',
    'asst name': '系列名称', 'asst no.': '系列编号', 'asst no': '系列编号',
    'package age grade': '包装标注年龄', 'test age grade': '测试适用年龄',
    'section': '章节', 'section no.': '章节编号', 'section affected': '涉及章节',
    'issued by': '编制', 'reviewed by': '审核', 'approved by': '批准', 'preliminary': '初版',
    'revision': '修订', 'date': '日期', 'price factor': '价格系数',
    'package aesthetic requirement and defect scoring': '包装外观要求及缺陷判定',
    'master carton requirement and defect scoring': '外箱要求及缺陷判定',
    'individual product requirement and defect scoring': '单件产品要求及缺陷判定',
    'product functional requirement and defect scoring': '产品功能要求及缺陷判定',
    'new': '新制', 'tool': '模具',
}


def translate_image_texts(texts, direction, translate):
    values = list(texts)
    pending = {}
    for i, text in enumerate(texts):
        key = re.sub(r'\s+', ' ', text).strip().lower()
        if direction == 'en_to_zh' and key in TERMS:
            values[i] = TERMS[key]
        else:
            pending.setdefault(text, []).append(i)
    if pending:
        unique = list(pending)
        try:
            translated = translate(unique, direction)
        except ToolError as exc:
            if exc.code not in {'TRANSLATION_NUMBERS_CHANGED', 'TRANSLATION_IDENTIFIERS_CHANGED'}:
                raise
            # Isolate invalid model output. Preserve that source span; the
            # compositor reports it as unchanged instead of damaging the page.
            translated = []
            for text in unique:
                try:
                    translated.append(translate([text], direction)[0])
                except ToolError as individual:
                    if individual.code not in {'TRANSLATION_NUMBERS_CHANGED', 'TRANSLATION_IDENTIFIERS_CHANGED'}:
                        raise
                    translated.append(text)
        for text, value in zip(unique, translated, strict=True):
            for i in pending[text]:
                values[i] = value
    return values

"""Source-only review layout when an AI plan is incomplete or cannot be trusted.

This is explicitly a layout needing review, never represented as a successful AI
reconstruction. Every displayed value still cites a visible native cell.
"""
import re
from collections import defaultdict

from app.services import carton_mark_flexible as flow


def build(source,reason):
    from openpyxl.utils.cell import coordinate_to_tuple
    cells={c.id:c for c in source["cells"]};locations={c.location:c for c in source["cells"]}
    note_locations={n.location for n in source["notes"]};groups=[]
    rows=source.get("detail_rows",[])
    if rows:
        for row in rows:
            entries=sorted((cells[k] for k in row["cell_ids"]),key=lambda c:coordinate_to_tuple(c.location.rsplit("!",1)[1])[1])
            groups.append(entries)
    else:
        sheets=defaultdict(list)
        for cell in source["cells"]:
            if cell.kind!="reference_cell" and cell.location not in note_locations:sheets[cell.location.rsplit("!",1)[0]].append(cell)
        for sheet,entries in sheets.items():
            # Explicit native mark blocks already distinguish the faces. Keep
            # their entire body, rather than the first 25 worksheet cells, and
            # leave captions outside the printed content.
            blocks=defaultdict(set)
            for block in source.get('blocks',[]):
                if block['sheet']==sheet:blocks[block['start_row']].update(block['cell_ids'])
            if blocks:
                for _,keys in sorted(blocks.items()):groups.append([c for c in entries if c.id in keys])
            else:groups.append(entries[:25])
    records=[]
    for entries in groups[:30]:
        faces=defaultdict(list)
        for cell in entries:
            if cell.location in note_locations or cell.kind=="reference_cell":continue
            label=None
            if rows:
                sheet,coord=cell.location.rsplit("!",1);r,col=coordinate_to_tuple(coord)
                from openpyxl.utils import get_column_letter
                # The detail table header is above its first native data row.
                native_row=next(row for row in rows if cell.id in row["cell_ids"])
                heading=locations.get(f"{sheet}!{get_column_letter(col)}{native_row['header_row']}")
                if heading and heading.location not in note_locations:label=dict(source_id=heading.id,value=heading.text)
            face=source.get("ownership",{}).get(cell.id,"front")
            faces[face].append(dict(label=label,parts=[dict(source_id=cell.id,value=cell.text)],role="normal"))
        if not rows:
            for face,fields in faces.items():
                by_row=defaultdict(list)
                for field in fields:
                    cell=cells[field['parts'][0]['source_id']]
                    _,coord=cell.location.rsplit('!',1);r,col=coordinate_to_tuple(coord)
                    by_row[r].append((col,cell))
                paired=[]
                for _,entries in sorted(by_row.items()):
                    entries.sort(key=lambda item:item[0]);i=0
                    while i<len(entries):
                        cell=entries[i][1];parts=[];label=None
                        if re.search(r'[:：]\s*$',cell.text):
                            j=i+1
                            while j<len(entries) and not re.search(r'[:：]\s*$',entries[j][1].text):
                                parts.append(entries[j][1]);j+=1
                            if parts:label=cell;i=j
                            else:parts=[cell];i+=1
                        else:parts=[cell];i+=1
                        paired.append(dict(label=dict(source_id=label.id,value=label.text) if label else None,
                            parts=[dict(source_id=p.id,value=p.text) for p in parts],role='normal'))
                faces[face]=paired
        if faces:records.append(dict(panels=[dict(face=face,copies=2,logo=flow.constraints(source)["logo"],fields=faces[face][:40],barcodes=[],symbols=[]) for face in ('front','side') if face in faces]))
    if not records:raise flow.pilot.PilotError("原稿没有可确认的本次印刷字段，请核实工作表")
    raw=dict(template_id="source-flow-v1",paper="A3",orientation="landscape",records=records,notes=[],ignored_cells=[])
    import json
    plan=flow.validate(json.dumps(raw,ensure_ascii=False),source,review_mode=True,require_destinations=False)
    plan._warnings.insert(0,"AI排版建议未能通过核验，当前按原生单元格整理为待核对稿；请在页面选择、补充和核实箱面内容。原因："+reason)
    return plan

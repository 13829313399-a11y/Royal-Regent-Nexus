"""Bounded native face regions, including repeated and vertically stacked marks."""
import re
from collections import defaultdict,Counter
from openpyxl.utils.cell import coordinate_to_tuple


def regions(cells, table_starts):
    headers=defaultdict(list); positions={}; counts=defaultdict(lambda:defaultdict(set))
    for cell in cells:
        sheet,coord=cell.location.rsplit('!',1);row,col=coordinate_to_tuple(coord)
        positions[cell.id]=(sheet,row,col)
        text=cell.text.translate(str.maketrans({'嘜':'唛','側':'侧','両':'两','兩':'两'}))
        face=('front' if re.search(r'^\s*(?:(?:carton\s+)?(?:main|front)\s*mark(?:s|ing)?|[正主]唛)\s*(?:$|[:：(（\-–])',text,re.I)
              else 'side' if re.search(r'^\s*(?:(?:carton\s+)?side\s*mark(?:s|ing)?|侧唛|侧面)\s*(?:$|[:：(（\-–])',text,re.I) else None)
        if not face or row>=table_starts.get(sheet,float('inf')):continue
        count=re.search(r'(two|2|两|二|four|4|四|one|1|一)\s*(?:sides?|面)|[x×]\s*([124])\s*$',text,re.I)
        copies=None
        if count:
            value=(count[1] or count[2]).lower()
            copies={'two':2,'2':2,'两':2,'二':2,'four':4,'4':4,'四':4,'one':1,'1':1,'一':1}[value]
            counts[sheet][face].add(copies)
        headers[sheet].append(dict(row=row,col=col,face=face,copies=copies,header_id=cell.id))
    ownership={};blocks=[]
    for sheet,items in headers.items():
        # Caption baselines can differ by one or two rows across the same box.
        # Pair only opposing faces in distinct columns; genuine stacked marks
        # keep their separate row intervals.
        ordered=sorted(items,key=lambda h:(h['row'],h['col']))
        for index,h in enumerate(ordered):
            partner=next((other for other in ordered[index+1:] if 0<other['row']-h['row']<=2 and other['face']!=h['face'] and abs(other['col']-h['col'])>=2),None)
            if partner:partner['row']=h['row']
        rows=sorted({h['row'] for h in items})
        for i,start in enumerate(rows):
            end=rows[i+1] if i+1<len(rows) else table_starts.get(sheet,float('inf'))
            same=[h for h in items if h['row']==start]
            if len(same)==2 and {h['face'] for h in same}=={'front','side'}:
                same.sort(key=lambda h:h['col']);boundary=(same[0]['col']+same[1]['col'])/2
                label_rows=defaultdict(list)
                for cell in cells:
                    sh,r,c=positions[cell.id]
                    if sh==sheet and start<r<min(end,start+50) and len(cell.text)<50 and re.search(r'[a-zA-Z]',cell.text) and re.search(r'[:：]\s*$',cell.text):label_rows[r].append(c)
                starts=Counter(sorted(values)[1] for values in label_rows.values() if len(values)==2)
                if starts and starts.most_common(1)[0][1]>=2:boundary=starts.most_common(1)[0][0]-.5
                for h in same:
                    keys=[key for key,(sh,r,c) in positions.items() if sh==sheet and start<r<end and ((c<=boundary)==(h is same[0]))]
                    ownership.update({key:h['face'] for key in keys})
                    blocks.append(dict(sheet=sheet,start_row=start,end_row=None if end==float('inf') else end,**h,cell_ids=keys))
            elif len(same)==1:
                h=same[0];keys=[key for key,(sh,r,c) in positions.items() if sh==sheet and start<r<end]
                ownership.update({key:h['face'] for key in keys})
                blocks.append(dict(sheet=sheet,start_row=start,end_row=None if end==float('inf') else end,**h,cell_ids=keys))
    copies={sheet:{face:next(iter(values)) for face,values in faces.items() if len(values)==1} for sheet,faces in counts.items()}
    return ownership,copies,blocks

import { describe, it, expect } from 'vitest';
import { createCanvas } from 'canvas';
import { resolve } from 'node:path';
import { prepareRegions, renderDocument, splitRuledRegion, splitMixedWords, verifiedWordParts, documentWordCrops, documentOcrRetry, acceptDocumentOcrRetry, registerDocumentFont, type Region } from '../../server/documentTypeset';

registerDocumentFont(resolve('server/dist'));
const region=(text:string,x:number,width:number):Region=>({id:text,sourceText:text,box:{x,y:40,width,height:30},prob:.99,method:'native'});
describe('document-safe typesetting',()=>{
  it('verifies a faint cut separator from pixels and retains numeric and material code pixels',()=>{
    const source=createCanvas(400,130),c=source.getContext('2d');
    c.fillStyle='white';c.fillRect(0,0,400,130);c.fillStyle='black';c.font='24px Arial';
    c.fillText('Cut',20,64);c.fillText('2',85,64);c.fillRect(120,53,8,2);c.fillText('BR',150,64);c.fillText('Tricot',210,64);
    const parent={...region('Cut 2 - BR Tricot',18,280),method:'ocr',direction:'h'};
    const parts=[region('',18,48),region('',80,25),region('',115,20),region('',145,40),region('',205,90)].map((r,i)=>({...r,id:`part-${i}`,method:'ocr'}));
    const recognized=new Map(parts.filter((_,i)=>i!==2).map((r,i)=>[r.id,{...r,sourceText:['Cut','2','BR','Tricot'][i],prob:.99}]));
    recognized.get(parts[0].id)!.direction='v';
    const verified=verifiedWordParts(source,parent,parts,recognized)!;
    expect(verified.map(r=>r.sourceText)).toEqual(['Cut','2','-','BR','Tricot']);
    expect(verified[0].direction).toBe('h');
    const regions=prepareRegions(verified,'en_to_zh');
    regions[0].translatedText='裁';regions[4].translatedText='经编布';
    const output=renderDocument(source,regions).getContext('2d');
    expect(regions[0].rendered).toBe(true);expect(regions[4].rendered).toBe(true);
    for(const [x,width] of [[78,30],[113,25],[143,44]])expect(output.getImageData(x,35,width,40).data).toEqual(c.getImageData(x,35,width,40).data);
    recognized.set(parts[1].id,{...parts[1],sourceText:'3',prob:.999});
    expect(verifiedWordParts(source,parent,parts,recognized)).toBeUndefined();
    c.clearRect(115,40,20,30);
    expect(verifiedWordParts(source,parent,parts,recognized)).toBeUndefined();
  });
  it('retries low-contrast captions on a copy and rejects changed quantities',()=>{
    const source=createCanvas(400,130),c=source.getContext('2d');
    c.fillStyle='#221f20';c.fillRect(0,0,400,130);c.fillStyle='#e41345';c.font='24px Arial';c.fillText('EYE',20,64);
    const before=source.toBuffer();
    const parent={...region('EYE',18,62),method:'ocr',prob:.96};
    const retry=documentOcrRetry(source,[parent,{...region('Q91075',200,95),method:'ocr'},region('HEAD',100,70)]);
    expect(retry.regions).toHaveLength(1);expect(source.toBuffer()).toEqual(before);
    const data=retry.canvas.getContext('2d').getImageData(18,40,62,30).data;
    expect(Array.from(data).some(v=>v===0)).toBe(true);expect(Array.from(data).some(v=>v===255)).toBe(true);
    expect(retry.regions[0].fgColor?.[0]).toBeGreaterThan(150);expect(retry.regions[0].fgColor?.[1]).toBeLessThan(70);
    const cut={...parent,sourceText:'Cut 2 - White Plus!'};
    expect(acceptDocumentOcrRetry(cut,{...parent,sourceText:'Cut 2 - White Plush',prob:.99})).toBe(true);
    expect(acceptDocumentOcrRetry(cut,{...parent,sourceText:'Cut 3 - White Plush',prob:.999})).toBe(false);
    expect(acceptDocumentOcrRetry(cut,{...parent,sourceText:'Cut 2 - White Plush',prob:.96})).toBe(false);
    expect(acceptDocumentOcrRetry({...cut,sourceText:'Cut 2 Q91075 Plush'},{...parent,sourceText:'Cut 2 R91075 Plush',prob:.999})).toBe(false);
    expect(documentOcrRetry(source,[{...parent,sourceText:''}]).regions).toHaveLength(1);
    expect(documentOcrRetry(source,[{...parent,prob:.999}]).regions).toHaveLength(0);
  });
  it('includes a clipped material suffix for recognition without expanding into adjacent quantities',()=>{
    const source=createCanvas(400,120),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,400,120);
    c.fillStyle='black';c.fillRect(260,45,4,12);c.fillRect(269,45,5,12);
    const word={...region('Plush',200,60),method:'ocr'},neighbor=region('2',269,20);
    const crops=documentWordCrops(source,[word],[neighbor]);
    const b=crops[0].box;
    expect(b.x+b.width).toBeGreaterThanOrEqual(264);expect(b.x+b.width).toBeLessThan(269);
    expect(word.box).toEqual({x:200,y:40,width:60,height:30});
  });
  it('accepts a verified material suffix only for cut captions while quantities and material codes stay fixed',()=>{
    const source=createCanvas(400,130),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,400,130);
    const parts=['Cut','2','BR','Plush'].map((text,i)=>({...region(text,20+i*80,70),id:`part-${i}`,method:'ocr',prob:.99}));
    const recognized=new Map(parts.map(r=>[r.id,r]));
    expect(verifiedWordParts(source,region('Cut 2 BR Plus!',20,310),parts,recognized)?.map(r=>r.sourceText)).toEqual(['Cut','2','BR','Plush']);
    expect(verifiedWordParts(source,region('Quantity 2 BR Plus!',20,310),parts,recognized)).toBeUndefined();
    expect(verifiedWordParts(source,region('Cut 3 BR Plus!',20,310),parts,recognized)).toBeUndefined();
    expect(verifiedWordParts(source,region('Cut 2 PVC Plus!',20,310),parts,recognized)).toBeUndefined();
    recognized.set(parts[3].id,{...parts[3],prob:.96});
    expect(verifiedWordParts(source,region('Cut 2 BR Plus!',20,310),parts,recognized)).toBeUndefined();
  });
  it('allows captions next to detected direction arrows without erasing the arrow',()=>{
    const source=createCanvas(220,170),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,220,170);
    c.fillStyle='#d21941';c.font='24px Arial';c.fillText('ARM',30,64);
    c.fillStyle='black';c.fillRect(58,76,2,50);
    const label={...region('ARM',28,62),method:'ocr'};
    const arrow={...region('<>',48,25),box:{x:48,y:68,width:25,height:68},method:'ocr'};
    const regions=prepareRegions([label,arrow],'en_to_zh');
    expect(regions[0].skipReason).toBeUndefined();expect(regions[1].skipReason).toBe('diagram');
    regions[0].translatedText='手臂';const output=renderDocument(source,regions);
    expect(regions[0].rendered).toBe(true);
    expect(output.getContext('2d').getImageData(47,67,27,70).data).toEqual(c.getImageData(47,67,27,70).data);
  });
  it('translates ordinary colored captions while retaining color codes and uncertain OCR',()=>{
    const colored=(text:string):Region=>({...region(text,20,180),method:'ocr',fgColor:[210,25,65]});
    for(const text of ['FRONT','Collar must be present','Show a definite']) {
      expect(prepareRegions([colored(text)],'en_to_zh')[0].skipReason).toBeUndefined();
    }
    expect(prepareRegions([colored('PANTONE')],'en_to_zh')[0].skipReason).toBe('protected');
    expect(prepareRegions([{...colored('FRONT'),prob:.7}],'en_to_zh')[0].skipReason).toBe('low-confidence');
  });
  it('renders a colored heading in its original foreground color without changing adjacent numbers',()=>{
    const source=createCanvas(400,150),c=source.getContext('2d');
    c.fillStyle='white';c.fillRect(0,0,400,150);c.fillStyle='rgb(210,25,65)';c.font='24px Arial';
    c.fillText('FRONT RIGHT',20,64);c.fillText('3/4',220,64);
    const regions=prepareRegions([{...region('FRONT RIGHT',18,185),method:'ocr',fgColor:[210,25,65]},region('3/4',218,70)],'en_to_zh');
    regions[0].translatedText='右前方';const output=renderDocument(source,regions),d=output.getContext('2d');
    expect(regions[0].rendered).toBe(true);
    expect(d.getImageData(215,30,80,50).data).toEqual(c.getImageData(215,30,80,50).data);
    const pixels=d.getImageData(20,40,180,30).data;
    expect(Array.from({length:pixels.length/4},(_,i)=>[pixels[i*4],pixels[i*4+1],pixels[i*4+2]])
      .some(rgb=>rgb[0]===210&&rgb[1]===25&&rgb[2]===65)).toBe(true);
  });
  it('retains the curved edge of a dark piece surrounding a red caption',()=>{
    const source=createCanvas(180,100),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,180,100);
    c.fillStyle='#221f20';c.beginPath();c.ellipse(65,48,45,17,0,0,Math.PI*2);c.fill();
    c.fillStyle='#e41345';c.font='20px Arial';c.fillText('EYE',40,56);
    // A measured OCR foreground can differ from the saturated glyph center.
    const r={...region('EYE',40,50),box:{x:40,y:35,width:50,height:25},method:'ocr',fgColor:[205,60,77],translatedText:'一'};
    const output=renderDocument(source,[r]);expect(r.rendered).toBe(true);
    const before=c.getImageData(0,0,180,100).data,after=output.getContext('2d').getImageData(0,0,180,100).data;
    for(let y=0;y<100;y++)for(let x=0;x<180;x++) {
      if(x>=39&&x<=91&&y>=34&&y<=61)continue;
      const p=(y*180+x)*4;expect(after.slice(p,p+4)).toEqual(before.slice(p,p+4));
    }
    const remaining=output.getContext('2d').getImageData(66,35,24,25).data;
    expect(Array.from({length:remaining.length/4},(_,i)=>remaining[i*4]-remaining[i*4+1]).some(v=>v>60)).toBe(false);
  });
  it('isolates a separator joined to a cut quantity without leaving Cut protected',()=>{
    const source=createCanvas(250,120),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,250,120);
    c.fillStyle='black';c.font='24px Arial';c.fillText('Cut',20,64);c.fillText('2',85,64);c.fillRect(120,53,8,2);
    const parts=splitMixedWords(source,{...region('Cut 2-',18,115),method:'ocr'});
    expect(parts).toHaveLength(3);
  });
  it('cuts uppercase captions with fractions at actual word gaps for verified re-OCR',()=>{
    const source=createCanvas(500,120),c=source.getContext('2d');
    c.fillStyle='white';c.fillRect(0,0,500,120);c.fillStyle='#d21941';c.font='24px Arial';
    const text='FRONT RIGHT 3/4';c.fillText(text,20,64);
    const parts=splitMixedWords(source,{...region(text,18,c.measureText(text).width+4),method:'ocr'});
    expect(parts).toHaveLength(3);
    expect(parts.every(p=>p.sourceText==='')).toBe(true);
    expect(parts[2].box.x).toBeGreaterThan(20+c.measureText('FRONT RIGHT').width);
    expect(splitMixedWords(source,{...region('Q91075',18,100),method:'ocr'})).toHaveLength(1);
  });
  it('never translates standalone or inline numbers, model IDs, hex colors and units',()=>{
    for(const text of ['00123','4.5"','0.05mm','Quantity 123','Q91075','#5f5075','5265C','PANTONE']) {
      expect(prepareRegions([region(text,10,100)],'en_to_zh')[0].skipReason).toBe('protected');
    }
  });
  it('preserves every numeric pixel and all pixels outside the bounded translated label',()=>{
    const source=createCanvas(400,150),c=source.getContext('2d');
    c.fillStyle='white';c.fillRect(0,0,400,150);c.fillStyle='black';c.font='24px Arial';
    c.fillText('Quantity',20,64);c.fillText('00123',180,64);c.fillRect(0,100,400,2);
    const regions=prepareRegions([region('Quantity',18,115),region('00123',178,95)],'en_to_zh');
    regions[0].translatedText='数量';const output=renderDocument(source,regions);
    expect(regions[0].rendered).toBe(true);
    expect(output.getContext('2d').getImageData(170,30,110,50).data).toEqual(c.getImageData(170,30,110,50).data);
    const before=c.getImageData(0,0,400,150).data,after=output.getContext('2d').getImageData(0,0,400,150).data;
    let changed=0;
    for(let y=0;y<150;y++)for(let x=0;x<400;x++)for(let k=0;k<4;k++) {
      const p=(y*400+x)*4+k;
      if(before[p]!==after[p]) {changed++;expect(x).toBeGreaterThanOrEqual(14);expect(x).toBeLessThan(138);expect(y).toBeGreaterThanOrEqual(36);expect(y).toBeLessThan(74);}
    }
    expect(changed).toBeGreaterThan(0);
  });
  it('leaves nonfitting or unchanged translations byte-for-byte intact',()=>{
    const source=createCanvas(160,100),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,160,100);
    c.fillStyle='black';c.font='20px Arial';c.fillText('Hair',20,62);
    const r=region('Hair',18,45);r.translatedText='这是一段完全无法放入该短标签的过长翻译';
    const output=renderDocument(source,[r]);
    expect(r.skipReason).toBe('does-not-fit');expect(output.toBuffer()).toEqual(source.toBuffer());
  });
  it('splits a cross-cell OCR candidate at the actual vertical rule',()=>{
    const source=createCanvas(300,150),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,300,150);
    c.fillStyle='black';c.fillRect(140,0,2,150);
    const split=splitRuledRegion(source,{...region('gradation 2017C',30,220),...{quad:[{x:30,y:40},{x:250,y:40},{x:250,y:70},{x:30,y:70}]}});
    expect(split).toHaveLength(2);expect(split[0].box.x+split[0].box.width).toBeLessThan(141);expect(split[1].box.x).toBeGreaterThan(141);
    expect((split[0] as unknown as {quad:unknown}).quad).toBeUndefined();
  });
  it('does not erase ambiguous overlapping labels',()=>{
    const regions=prepareRegions([region('Hair',20,100),region('001',95,90)],'en_to_zh');
    expect(regions[0].skipReason).toBe('overlap');
  });
  it('cleans visible native glyph ink extending above PDF font metric boxes',()=>{
    const source=createCanvas(200,120),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,200,120);
    c.fillStyle='black';c.font='24px Arial';c.fillText('Page',20,54);
    const r=region('Page',20,90);r.translatedText='一';
    const result=renderDocument(source,[r]);expect(r.rendered).toBe(true);
    const d=result.getContext('2d').getImageData(20,30,90,10).data;
    expect([...d].every(value=>value===255)).toBe(true);
  });
  it('retains a table rule touching the original text underline',()=>{
    const source=createCanvas(300,120),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,300,120);
    c.fillStyle='black';c.font='24px Arial';c.fillText('Packaging',20,64);c.fillRect(18,66,180,2);
    const r=region('Packaging',18,180);r.translatedText='包装要求';
    const result=renderDocument(source,[r]);expect(r.rendered).toBe(true);
    expect(result.getContext('2d').getImageData(18,66,180,2).data).toEqual(c.getImageData(18,66,180,2).data);
  });
  it('preserves small cell borders and anchors text inside the original label',()=>{
    const source=createCanvas(180,130),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,180,130);
    c.fillStyle='black';c.fillRect(14,0,2,130);c.fillRect(0,34,180,2);c.font='20px Arial';c.fillText('Hair',22,62);
    const r={...region('Hair',20,58),method:'ocr',translatedText:'头发'};
    const result=renderDocument(source,[r]),d=result.getContext('2d');expect(r.rendered).toBe(true);
    expect(d.getImageData(14,0,2,130).data).toEqual(c.getImageData(14,0,2,130).data);
    expect(d.getImageData(0,34,180,2).data).toEqual(c.getImageData(0,34,180,2).data);
  });
  it('fits Chinese above a lower table rule instead of drawing across it',()=>{
    const source=createCanvas(240,120),c=source.getContext('2d');c.fillStyle='white';c.fillRect(0,0,240,120);
    c.fillStyle='black';c.font='24px Arial';c.fillText('Main Unit',20,54);c.fillRect(0,62,240,2);
    const r=region('Main Unit',20,130);r.translatedText='主要部件';
    const result=renderDocument(source,[r]),d=result.getContext('2d');expect(r.rendered).toBe(true);
    expect([...d.getImageData(20,61,130,1).data].every(v=>v===255)).toBe(true);
    expect(d.getImageData(0,62,240,2).data).toEqual(c.getImageData(0,62,240,2).data);
  });
});

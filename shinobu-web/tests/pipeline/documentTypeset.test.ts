import { describe, it, expect } from 'vitest';
import { createCanvas } from 'canvas';
import { resolve } from 'node:path';
import { prepareRegions, renderDocument, splitRuledRegion, registerDocumentFont, type Region } from '../../server/documentTypeset';

registerDocumentFont(resolve('server/dist'));
const region=(text:string,x:number,width:number):Region=>({id:text,sourceText:text,box:{x,y:40,width,height:30},prob:.99,method:'native'});
describe('document-safe typesetting',()=>{
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

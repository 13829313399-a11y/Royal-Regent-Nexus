/** Conservative document compositor. No generative erase, expansion or bubble layout. */
import { createCanvas, type Canvas } from 'canvas';
import { existsSync } from 'node:fs';
import { registerFont } from 'canvas';
import { resolve } from 'node:path';

export function registerDocumentFont(root:string) {
  const windows=process.env.WINDIR ?? 'C:/Windows';
  const fallback=resolve(root,'fonts/SourceHanSansCN-VF.ttf');
  const regular=[`${windows}/Fonts/msyh.ttc`,'/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',fallback].find(existsSync)!;
  const bold=[`${windows}/Fonts/msyhbd.ttc`,'/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',regular].find(existsSync)!;
  registerFont(regular,{family:'RR Document Sans',weight:'normal'});
  registerFont(bold,{family:'RR Document Sans',weight:'bold'});
}

export type Region = {
  id: string; sourceText: string; translatedText?: string;
  box: { x: number; y: number; width: number; height: number };
  prob?: number; fontSize?: number; bold?: boolean; protected?: boolean; method?: string;
  direction?: string; skipReason?: string; rendered?: boolean;
  fgColor?: number[];
};
const identifiers = /\d|https?:\/\/|www\.|@|^[#＃]|^(?:PANTON[E]?|UPC|CE|CPSC|ASTM|EN|ISO|AQL|MIL|QA|QC|PVC|ABS|PP|PET|PE|EEC|EC|EU|USA|S\/S|PNP|PUP|HOLOLIVE|JAKKS|TM|Sa|Cr|Maj|Min)$/i;
export function preserveReason(region: Region, direction: string): string | undefined {
  const text = region.sourceText.trim();
  if (region.protected || identifiers.test(text)) return 'protected';
  if (region.method !== 'native' && region.fgColor && Math.max(...region.fgColor)-Math.min(...region.fgColor)>35) return 'styled-text';
  if (!(direction === 'zh_to_en' ? /[\u3400-\u9fff]/ : /[A-Za-z]{2}/).test(text)) return 'not-source-language';
  if (region.direction === 'v' || region.box.height > region.box.width * 1.8) return 'vertical';
  if ((region.prob ?? 1) < .90) return 'low-confidence';
  if (/\ufffd|\(cid:/.test(text)) return 'invalid-text';
  return undefined;
}

export function overlap(a: Region['box'], b: Region['box']): number {
  return Math.max(0, Math.min(a.x+a.width,b.x+b.width)-Math.max(a.x,b.x)) *
    Math.max(0, Math.min(a.y+a.height,b.y+b.height)-Math.max(a.y,b.y));
}

export function prepareRegions(regions: Region[], direction: string): Region[] {
  const unique: Region[] = [];
  for (const original of regions) {
    const region = { ...original, box: { ...original.box }, method: original.method ?? 'ocr' };
    if (unique.some(other => overlap(region.box, other.box) / Math.min(region.box.width*region.box.height,other.box.width*other.box.height) > .8)) continue;
    region.skipReason = preserveReason(region, direction);
    // Captions directly below product IDs are names, not prose. Preserve the
    // original spelling instead of feeding short proper names to a text model.
    if(region.method!=='native'&&/^[A-Z][A-Z'’ -]{5,}$/.test(region.sourceText)&&regions.some(code=>
      /^\d{3,}[A-Z]*$/.test(code.sourceText)&&region.box.y>=code.box.y+code.box.height*.6&&
      region.box.y-code.box.y-code.box.height<code.box.height*1.7&&
      Math.abs(region.box.x+region.box.width/2-code.box.x-code.box.width/2)<Math.max(code.box.width,region.box.width*.4))) region.skipReason='protected';
    unique.push(region);
  }
  // An ambiguous overlap must not erase an adjacent value or another label.
  for (const region of unique) {
    if (!region.skipReason && unique.some(other => other !== region && overlap(region.box, other.box) > 2)) region.skipReason = 'overlap';
  }
  for(const region of unique.filter(r=>r.method!=='native'&&!r.skipReason)) {
    const peers=unique.filter(r=>r.method!=='native'&&!r.skipReason&&Math.abs(r.box.x-region.box.x)<region.box.height*.6&&r.box.height/region.box.height>.65&&r.box.height/region.box.height<1.5);
    if(peers.length>=4)region.fontSize=peers.map(r=>r.box.height).sort((a,b)=>a-b)[Math.floor(peers.length/2)]*.94;
  }
  return unique;
}

/** OCR occasionally joins words across a table rule. Re-recognize each cell. */
export function splitRuledRegion(source: Canvas, region: Region): Region[] {
  if (!/[A-Za-z]/.test(region.sourceText) || !/\d/.test(region.sourceText)) return [region];
  const b=region.box, x=Math.max(0,Math.floor(b.x)), y=Math.max(0,Math.floor(b.y-b.height));
  const w=Math.min(source.width-x,Math.ceil(b.width)), h=Math.min(source.height-y,Math.ceil(b.height*3));
  if(w<20||h<12) return [region];
  const d=source.getContext('2d').getImageData(x,y,w,h).data;
  const cuts:number[]=[];
  for(let col=5;col<w-5;col++) {
    let count=0;
    for(let row=0;row<h;row++) {const at=(row*w+col)*4;if(Math.max(d[at],d[at+1],d[at+2])<90)count++;}
    if(count/h>.9 && (!cuts.length||col-cuts[cuts.length-1]>5)) cuts.push(col);
  }
  const edges=[0,...cuts,w];
  if(edges.length===2) return [region];
  return edges.slice(0,-1).flatMap((left,i)=>edges[i+1]-left>12?[{...region,id:`${region.id}-cell-${i}`,
    quad:undefined,box:{x:x+left+2,y:b.y,width:edges[i+1]-left-4,height:b.height},sourceText:'',translatedText:''}]:[]);
}

/** Candidate word cuts use observed whitespace, never proportional text widths.
 * The caller must re-OCR and verify the concatenated text before accepting. */
export function splitMixedWords(source:Canvas,region:Region):Region[] {
  if(!/\d/.test(region.sourceText)||!/[a-z]/.test(region.sourceText)) return [region];
  const count=region.sourceText.trim().split(/\s+/).length;
  if(count<2||count>24||region.direction==='v') return [region];
  const b=region.box,x=Math.max(0,Math.floor(b.x)),y=Math.max(0,Math.floor(b.y));
  const w=Math.min(source.width-x,Math.ceil(b.width)),h=Math.min(source.height-y,Math.ceil(b.height));
  const data=source.getContext('2d').getImageData(x,y,w,h).data;
  const values:number[]=[];
  for(let p=0;p<w*h;p++)values.push((data[p*4]+data[p*4+1]+data[p*4+2])/3);
  values.sort((a,b)=>a-b);const bg=values[Math.floor(values.length*.6)];
  const gaps:{start:number;end:number}[]=[];let start=-1;
  for(let col=0;col<=w;col++) {
    let ink=0;
    if(col<w)for(let row=0;row<h;row++) {const p=(row*w+col)*4;if(Math.abs((data[p]+data[p+1]+data[p+2])/3-bg)>35)ink++;}
    const blank=col<w&&ink<=Math.floor(h*.015);
    if(blank&&start<0)start=col;
    if(!blank&&start>=0){if(start>1&&col<w-1&&col-start>=Math.max(3,h*.08))gaps.push({start,end:col});start=-1;}
  }
  if(gaps.length<count-1)return [region];
  const selected=gaps.sort((a,b)=>(b.end-b.start)-(a.end-a.start)).slice(0,count-1).sort((a,b)=>a.start-b.start);
  const cuts=[0,...selected.map(g=>(g.start+g.end)/2),w];
  return cuts.slice(0,-1).map((left,i)=>({...region,id:`${region.id}-word-${i}`,sourceText:'',translatedText:'',quad:undefined,
    box:{x:x+left,y:b.y,width:cuts[i+1]-left,height:b.height}}));
}

function paddedBox(region:Region, all:Region[], source:Canvas):Region['box'] {
  // PDF font metrics and OCR boxes can both undershoot visible glyph ink.
  // Neighbor bounds and protected pixel restoration constrain the cleanup.
  const b=region.box, pad=Math.max(1,Math.min(region.method==='native'?12:32,b.height*.35));
  let l=Math.max(0,b.x-pad),t=Math.max(0,b.y-pad),r=Math.min(source.width,b.x+b.width+pad),bt=Math.min(source.height,b.y+b.height+pad);
  for(const other of all) if(other!==region) {
    const o=other.box;
    if(Math.min(bt,o.y+o.height)>Math.max(t,o.y)) {
      if(o.x+o.width<=b.x) l=Math.max(l,o.x+o.width+.5);
      if(o.x>=b.x+b.width) r=Math.min(r,o.x-.5);
    }
    if(Math.min(r,o.x+o.width)>Math.max(l,o.x)) {
      if(o.y+o.height<=b.y) t=Math.max(t,o.y+o.height+.5);
      if(o.y>=b.y+b.height) bt=Math.min(bt,o.y-.5);
    }
  }
  return {x:l,y:t,width:r-l,height:bt-t};
}

function colorDistance(a: number[], b: number[]): number {
  return Math.max(...a.map((v,i) => Math.abs(v-b[i])));
}

export function renderDocument(source: Canvas, regions: Region[]): Canvas {
  const output = createCanvas(source.width, source.height);
  const ctx = output.getContext('2d'); ctx.drawImage(source, 0, 0);
  const original = source.getContext('2d');
  for (const region of regions) {
    if (region.skipReason) continue;
    if (!region.translatedText || region.translatedText.trim() === region.sourceText.trim()) {region.skipReason='unchanged';continue;}
    const b = paddedBox(region,regions,source);
    const x = Math.max(0, Math.floor(b.x)), y = Math.max(0, Math.floor(b.y));
    const w = Math.min(source.width-x, Math.ceil(b.x+b.width)-x), h = Math.min(source.height-y, Math.ceil(b.y+b.height)-y);
    if (w < 3 || h < 5) { region.skipReason = 'too-small'; continue; }
    const pixels = original.getImageData(x,y,w,h);
    // A flat background is required; textured artwork stays intact for review.
    const bins = new Map<string,{ count: number; sum: number[] }>();
    for (let i=0;i<pixels.data.length;i+=4) {
      const rgb = Array.from(pixels.data.slice(i,i+3)); const key=rgb.map(v=>v>>4).join(',');
      const bin=bins.get(key) ?? {count:0,sum:[0,0,0]}; bin.count++; rgb.forEach((v,c)=>bin.sum[c]+=v); bins.set(key,bin);
    }
    const dominant = [...bins.values()].sort((a,b)=>b.count-a.count)[0];
    const bg = dominant.sum.map(v=>Math.round(v/dominant.count));
    let flat=0; const ink = new Uint8Array(w*h);
    for (let p=0;p<w*h;p++) {
      const distance=colorDistance(Array.from(pixels.data.slice(p*4,p*4+3)),bg);
      if (distance<25) flat++; if (distance>22) ink[p]=1;
    }
    if (flat/(w*h)<.50) { region.skipReason='complex-background'; continue; }
    // Reject large illustration components. Keep straight rules/underlines.
    const seen=new Uint8Array(w*h), erase=new Uint8Array(w*h), rules=new Uint8Array(w*h); let complex=false;
    const cx=Math.max(0,x-4),cy=Math.max(0,y-4),cw=Math.min(source.width-cx,w+x-cx+4),ch=Math.min(source.height-cy,h+y-cy+4);
    const context=original.getImageData(cx,cy,cw,ch).data;
    const isInk=(px:number,py:number)=>{
      if(px<cx||py<cy||px>=cx+cw||py>=cy+ch)return false;
      const at=((py-cy)*cw+px-cx)*4;
      return Math.max(Math.abs(context[at]-bg[0]),Math.abs(context[at+1]-bg[1]),Math.abs(context[at+2]-bg[2]))>12;
    };
    // A rule continuing beyond the crop is never a glyph, even if it touches
    // letters or the crop is narrower than its text height.
    for(let col=0;col<w;col++)if(isInk(x+col,y-3)&&isInk(x+col,y+h+2)) {
      let count=0;for(let row=0;row<h;row++)if(ink[row*w+col])count++;
      if(count>h*.8)for(let row=0;row<h;row++)if(isInk(x+col,y+row)){rules[row*w+col]=1;ink[row*w+col]=0;}
    }
    for(let row=0;row<h;row++)if(isInk(x-3,y+row)&&isInk(x+w+2,y+row)) {
      let count=0;for(let col=0;col<w;col++)if(ink[row*w+col])count++;
      if(count>w*.8)for(let col=0;col<w;col++)if(isInk(x+col,y+row)){rules[row*w+col]=1;ink[row*w+col]=0;}
    }
    // Underlines can touch descenders and otherwise form one enormous component.
    // Detach observed continuous rules before classifying text components.
    for(let row=0;row<h;row++) {
      let left=-1;
      for(let col=0;col<=w;col++) {
        if(col<w&&ink[row*w+col]) {if(left<0)left=col;}
        else if(left>=0) {
          if(col-left>Math.max(h*2.5,w*.5))for(let cx=left;cx<col;cx++) {
            rules[row*w+cx]=1;ink[row*w+cx]=0;
          }
          left=-1;
        }
      }
    }
    for (let start=0;start<ink.length;start++) {
      if (!ink[start] || seen[start]) continue;
      const pending=[start], component:number[]=[]; seen[start]=1;
      let l=w,t=h,r=0,bt=0;
      for (let k=0;k<pending.length;k++) {
        const p=pending[k], px=p%w, py=Math.floor(p/w); component.push(p); l=Math.min(l,px); r=Math.max(r,px); t=Math.min(t,py); bt=Math.max(bt,py);
        for (const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,-1],[1,-1],[-1,1]]) {
          const nx=px+dx,ny=py+dy,np=ny*w+nx;
          if(nx>=0&&nx<w&&ny>=0&&ny<h&&ink[np]&&!seen[np]) { seen[np]=1;pending.push(np); }
        }
      }
      const cw=r-l+1,ch=bt-t+1;
      const rule=(cw>h*2.5&&ch<=Math.max(3,h*.15)) || (ch>h*.85&&cw<=Math.max(2,h*.08));
      if (rule) {component.forEach(p=>rules[p]=1);continue;}
      if (region.method!=='native' && cw>h*3.5 && ch>h*.5) {complex=true;break;}
      component.forEach(p=>erase[p]=1);
    }
    if(complex) {region.skipReason='illustration';continue;}
    // Align to visible ink, since PDF font metric boxes can sit below the
    // actual letters. Nearby horizontal rules constrain the usable cell height.
    let inkTop=h,inkBottom=-1;
    for(let p=0;p<erase.length;p++)if(erase[p]){const row=Math.floor(p/w);inkTop=Math.min(inkTop,row);inkBottom=Math.max(inkBottom,row);}
    const center=inkBottom>=inkTop?y+(inkTop+inkBottom+1)/2:region.box.y+region.box.height/2;
    let top=y,bottom=y+h;
    for(let row=0;row<h;row++) {
      let count=0;for(let col=0;col<w;col++)count+=rules[row*w+col];
      if(count>Math.min(w*.65,region.box.width*.7)) {
        if(y+row<center)top=Math.max(top,y+row+2);
        else bottom=Math.min(bottom,y+row-1);
      }
    }
    const translated=region.translatedText.trim();
    const nominal=Math.min(region.fontSize ?? region.box.height*.94,b.height*.9);
    let size=nominal;
    const font=()=>`${region.bold ? 'bold ' : ''}${size}px "RR Document Sans"`;
    ctx.font=font(); let metrics=ctx.measureText(translated);
    const fit=Math.min(1,(region.box.width-1)/Math.max(1,metrics.width),Math.min(region.box.height+1,bottom-top)/Math.max(1,metrics.actualBoundingBoxAscent+metrics.actualBoundingBoxDescent));
    size*=fit;
    if (size<nominal*.64 || size<7) {region.skipReason='does-not-fit';continue;}
    ctx.font=font(); metrics=ctx.measureText(translated);
    // Replace only detected glyph pixels (+ one anti-alias pixel). Original
    // lines, surrounding artwork and every pixel outside the source box survive.
    const cleaned=original.getImageData(x,y,w,h);
    const radius=Math.max(1,Math.round(h*.018));
    for(let p=0;p<erase.length;p++) if(erase[p]) {
      const px=p%w,py=Math.floor(p/w);
      for(let dy=-radius;dy<=radius;dy++) for(let dx=-radius;dx<=radius;dx++) {
        const nx=px+dx,ny=py+dy;
        if(nx>=0&&nx<w&&ny>=0&&ny<h) {
          const at=(ny*w+nx)*4; bg.forEach((v,c)=>cleaned.data[at+c]=v);
        }
      }
    }
    ctx.putImageData(cleaned,x,y);
    ctx.save(); ctx.beginPath(); ctx.rect(x,y,w,h); ctx.clip();
    ctx.fillStyle=(bg[0]*.299+bg[1]*.587+bg[2]*.114)>140?'#202124':'#ffffff';
    ctx.textBaseline='alphabetic';
    const baseline=Math.max(top+metrics.actualBoundingBoxAscent,Math.min(bottom-metrics.actualBoundingBoxDescent,
      center+(metrics.actualBoundingBoxAscent-metrics.actualBoundingBoxDescent)/2));
    ctx.fillText(translated,region.box.x+Math.max(0,metrics.actualBoundingBoxLeft),baseline);
    ctx.restore();
    const painted=ctx.getImageData(x,y,w,h);
    for(let p=0;p<rules.length;p++) if(rules[p]) for(let c=0;c<4;c++)painted.data[p*4+c]=pixels.data[p*4+c];
    ctx.putImageData(painted,x,y);
    region.rendered=true;
    // Exact modification bounds are included in the private review artifact.
    Object.assign(region,{renderBox:b});
  }
  // Freeze all protected boxes after compositing as an additional pixel-level
  // guard against antialias padding close to a number or a code.
  for(const region of regions.filter(r=>r.skipReason==='protected')) {
    const b=region.box,x=Math.max(0,Math.floor(b.x)-1),y=Math.max(0,Math.floor(b.y)-1);
    const w=Math.min(source.width-x,Math.ceil(b.x+b.width)+1-x),h=Math.min(source.height-y,Math.ceil(b.y+b.height)+1-y);
    if(w>0&&h>0)ctx.putImageData(original.getImageData(x,y,w,h),x,y);
  }
  return output;
}

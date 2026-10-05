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
const identifiers = /\d|https?:\/\/|www\.|@|^[#＃]|^(?:PANTON[E]?|UPC|CE|CPSC|ASTM|EN|ISO|AQL|MIL|QA|QC|PVC|ABS|PP|PET|PE|BR|EEC|EC|EU|USA|S\/S|PNP|PUP|HOLOLIVE|JAKKS|PEANUTS|TM|Sa|Cr|Maj|Min)$/i;
const protectedTextTokens=(text:string)=>text.split(/\s+/).filter(t=>/[A-Za-z]/.test(t)&&identifiers.test(t)).map(t=>t.toUpperCase());
export function preserveReason(region: Region, direction: string): string | undefined {
  const text = region.sourceText.trim();
  if (region.protected || identifiers.test(text)) return 'protected';
  if (/^<[^A-Za-z0-9]{0,4}>$/.test(text) && region.box.height>region.box.width*1.8) return 'diagram';
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
    if (!region.skipReason && unique.some(other => other !== region && other.skipReason!=='diagram' && overlap(region.box, other.box) > 2)) region.skipReason = 'overlap';
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
  if(!/\d/.test(region.sourceText)||!/[A-Za-z]/.test(region.sourceText)) return [region];
  const cutInstruction=/Cut\s+\d+\b/i.test(region.sourceText);
  const words=cutInstruction ? region.sourceText.replace(/([A-Z])([A-Z][a-z])/g,'$1 $2').replace(/(\d)([-–—])/g,'$1 $2').replace(/([-–—])([A-Za-z])/g,'$1 $2') : region.sourceText;
  let count=words.trim().split(/\s+/).length;
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
  // OCR often omits a small trailing hyphen from "Cut 2 -". It remains a
  // visible separator; the caller verifies every letter and digit afterward.
  if(cutInstruction&&/^Cut\s+\d+$/i.test(words.trim())&&gaps.length>=count)count++;
  if(gaps.length<count-1)return [region];
  const selected=gaps.sort((a,b)=>(b.end-b.start)-(a.end-a.start)).slice(0,count-1).sort((a,b)=>a.start-b.start);
  const cuts=[0,...selected.map(g=>(g.start+g.end)/2),w];
  return cuts.slice(0,-1).map((left,i)=>({...region,id:`${region.id}-word-${i}`,sourceText:'',translatedText:'',quad:undefined,
    box:{x:x+left,y:b.y,width:cuts[i+1]-left,height:b.height}}));
}

/** A punctuation-only crop must be verified from pixels, not OCR confidence. */
export function observedSeparator(source:Canvas,region:Region):boolean {
  const b=region.box,x=Math.max(0,Math.floor(b.x)),y=Math.max(0,Math.floor(b.y));
  const w=Math.min(source.width-x,Math.ceil(b.width)),h=Math.min(source.height-y,Math.ceil(b.height));
  if(w<2||h<3)return false;
  const d=source.getContext('2d').getImageData(x,y,w,h).data;
  const bins=new Map<string,{count:number;color:number[]}>();
  for(let p=0;p<w*h;p++) {
    const rgb=[d[p*4],d[p*4+1],d[p*4+2]],key=rgb.map(v=>v>>4).join(',');
    const bin=bins.get(key)??{count:0,color:rgb};bin.count++;bins.set(key,bin);
  }
  const bg=[...bins.values()].sort((a,b)=>b.count-a.count)[0].color;
  let left=w,right=-1,top=h,bottom=-1,ink=0;
  for(let p=0;p<w*h;p++)if(colorDistance([d[p*4],d[p*4+1],d[p*4+2]],bg)>45) {
    left=Math.min(left,p%w);right=Math.max(right,p%w);top=Math.min(top,Math.floor(p/w));bottom=Math.max(bottom,Math.floor(p/w));ink++;
  }
  const width=right-left+1,height=bottom-top+1;
  return ink>=2&&width>=h*.12&&width<=h*.8&&height<=Math.max(3,h*.25)&&width>=height*1.5;
}

export function verifiedWordParts(source:Canvas,parent:Region,candidates:Region[],recognized:Map<string,Region>):Region[]|undefined {
  const parts:Region[]=[];
  for(const candidate of candidates) {
    const found=recognized.get(candidate.id);
    if(observedSeparator(source,candidate)) {
      parts.push({...candidate,sourceText:'-',protected:true,prob:1});
    } else if(found&&(found.prob??0)>=.90)parts.push({...found,box:{...candidate.box},direction:parent.direction});
    else return undefined;
  }
  const normalize=(s:string)=>s.toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]/g,'');
  const text=parts.map(p=>p.sourceText).join(' ');
  const cutInstruction=/Cut\s+\d+\b/i.test(parent.sourceText);
  const codesMatch=JSON.stringify(protectedTextTokens(text))===JSON.stringify(protectedTextTokens(parent.sourceText));
  if(normalize(text)===normalize(parent.sourceText)&&(!cutInstruction||codesMatch))return parts;
  // A cropped last letter may be misread by the full-line OCR. Only explicit
  // cut instructions can accept stronger word readings; quantities and known
  // material codes must still match, and every alphabetic crop needs >= .97.
  const numbers=(s:string)=>s.match(/\d+(?:[.,/]\d+)*/g)??[];
  return cutInstruction
    &&parts.filter(p=>/[A-Za-z]/.test(p.sourceText)).every(p=>(p.prob??0)>=.97)
    &&JSON.stringify(numbers(text))===JSON.stringify(numbers(parent.sourceText))
    &&codesMatch?parts:undefined;
}

/** Recognition may include glyph edges outside a tight OCR box; rendering
 * still uses the original word boundary, with protected pixels restored. */
export function documentWordCrops(source:Canvas,parts:Region[],neighbors:Region[]):Region[] {
  return parts.map(r=>{
    const all=[...parts,...neighbors],vertical=paddedBox(r,all,source,.12),horizontal=paddedBox(r,all,source);
    return {...r,quad:undefined,box:{...vertical,x:horizontal.x,width:horizontal.width}};
  });
}

function hasColoredStrokes(source:Canvas,region:Region):boolean {
  const b=region.box,x=Math.max(0,Math.floor(b.x)),y=Math.max(0,Math.floor(b.y));
  const w=Math.min(source.width-x,Math.ceil(b.width)),h=Math.min(source.height-y,Math.ceil(b.height));
  if(w<2||h<3)return false;
  const data=source.getContext('2d').getImageData(x,y,w,h).data;let ink=0;
  for(let p=0;p<w*h;p++)if(Math.max(data[p*4],data[p*4+1],data[p*4+2])-Math.min(data[p*4],data[p*4+1],data[p*4+2])>70)ink++;
  return ink>=14&&ink<w*h*.75;
}

/** Re-read ordinary document captions on a flat high-contrast copy only.
 * The original bitmap remains authoritative for rendering and protected pixels. */
export function documentOcrRetry(source:Canvas,regions:Region[]):{canvas:Canvas;regions:Region[]} {
  const canvas=createCanvas(source.width,source.height),ctx=canvas.getContext('2d');
  ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);
  const candidates=regions.filter(r=>r.method!=='native'&&!r.protected&&r.direction!=='v'&&r.box.height<=r.box.width*1.8
    &&(!r.sourceText?hasColoredStrokes(source,r):(r.prob??1)<.99&&/[A-Za-z]{2}/.test(r.sourceText))
    &&!identifiers.test(r.sourceText)).slice(0,96);
  const retried=candidates.map(r=>{
    const b=paddedBox(r,regions,source),x=Math.floor(b.x),y=Math.floor(b.y),w=Math.ceil(b.x+b.width)-x,h=Math.ceil(b.y+b.height)-y;
    const data=source.getContext('2d').getImageData(x,y,w,h),bins=new Map<string,{count:number;rgb:number[]}>();
    for(let p=0;p<w*h;p++) {
      const rgb=[...data.data.slice(p*4,p*4+3)],key=rgb.map(v=>v>>4).join(',');
      const bin=bins.get(key)??{count:0,rgb};bin.count++;bins.set(key,bin);
    }
    const colors=[...bins.values()].sort((a,b)=>b.count-a.count),bg=colors[0].rgb;
    const foreground=new Map<string,{count:number;rgb:number[]}>();
    for(let p=0;p<w*h;p++) {
      const px=x+p%w,py=y+Math.floor(p/w),rgb=[...data.data.slice(p*4,p*4+3)];
      if(px<r.box.x||px>=r.box.x+r.box.width||py<r.box.y||py>=r.box.y+r.box.height||colorDistance(rgb,bg)<=45)continue;
      const key=rgb.map(v=>v>>4).join(','),bin=foreground.get(key)??{count:0,rgb};bin.count++;foreground.set(key,bin);
    }
    const fg=r.fgColor??[...foreground.values()].sort((a,b)=>b.count-a.count)[0]?.rgb;
    for(let p=0;p<w*h;p++) {
      const value=colorDistance([...data.data.slice(p*4,p*4+3)],bg)>35?0:255;
      for(let c=0;c<3;c++)data.data[p*4+c]=value;
      data.data[p*4+3]=255;
    }
    ctx.putImageData(data,x,y);
    return {...r,id:`${r.id}-contrast`,sourceText:'',translatedText:'',fgColor:fg,quad:undefined,box:{x,y,width:w,height:h}};
  });
  return {canvas,regions:retried};
}

export function acceptDocumentOcrRetry(parent:Region,found:Region|undefined):boolean {
  const numbers=(s:string)=>s.match(/\d+(?:[.,/]\d+)*/g)??[];
  return !!found&&(found.prob??0)>=.97&&/[A-Za-z]{2}/.test(found.sourceText)
    &&JSON.stringify(numbers(found.sourceText))===JSON.stringify(numbers(parent.sourceText))
    &&JSON.stringify(protectedTextTokens(found.sourceText))===JSON.stringify(protectedTextTokens(parent.sourceText));
}

function paddedBox(region:Region, all:Region[], source:Canvas,ratio=.35):Region['box'] {
  // PDF font metrics and OCR boxes can both undershoot visible glyph ink.
  // Neighbor bounds and protected pixel restoration constrain the cleanup.
  const b=region.box, pad=Math.max(1,Math.min(region.method==='native'?12:32,b.height*ratio));
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
    const captionColor=region.fgColor;
    const colored=captionColor?.length===3&&captionColor.every(v=>Number.isFinite(v)&&v>=0&&v<=255)
      &&Math.max(...captionColor)-Math.min(...captionColor)>60&&colorDistance(captionColor,bg)>35;
    const isGlyphColor=(p:number)=>{
      if(!colored)return true;
      const vector=captionColor!.map((v,i)=>v-bg[i]),rgb=Array.from(pixels.data.slice(p*4,p*4+3));
      if(Math.max(...bg)-Math.min(...bg)<35&&Math.max(...rgb)-Math.min(...rgb)<14)return false;
      const strength=Math.max(0,Math.min(1,vector.reduce((s,v,i)=>s+v*(rgb[i]-bg[i]),0)/vector.reduce((s,v)=>s+v*v,0)));
      return colorDistance(rgb,bg.map((v,i)=>v+strength*vector[i]))<=45;
    };
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
      // Colored glyphs have a measured foreground. Neutral artwork or the
      // white surround of a dark curved piece must survive the same crop.
      component.forEach(p=>{if(isGlyphColor(p))erase[p]=1;else rules[p]=1;});
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
    const fg=region.fgColor;
    ctx.fillStyle=fg?.length===3&&fg.every(v=>Number.isFinite(v)&&v>=0&&v<=255)&&colorDistance(fg,bg)>35
      ? `rgb(${fg.join(',')})` : (bg[0]*.299+bg[1]*.587+bg[2]*.114)>140?'#202124':'#ffffff';
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
  for(const region of regions.filter(r=>r.skipReason==='protected'||r.skipReason==='diagram')) {
    const b=region.box,x=Math.max(0,Math.floor(b.x)-1),y=Math.max(0,Math.floor(b.y)-1);
    const w=Math.min(source.width-x,Math.ceil(b.x+b.width)+1-x),h=Math.min(source.height-y,Math.ceil(b.y+b.height)+1-y);
    if(w>0&&h>0)ctx.putImageData(original.getImageData(x,y,w,h),x,y);
  }
  return output;
}

/** Generic document compositor. Content completeness never depends on fitting. */
import {createCanvas, type Canvas} from 'canvas';
import type {Region} from './documentTypeset';

export type DocumentRegion = Region & {
  kind?:string; group?:string; translationStatus?:string; reviewNotes?:string[];
  lineBoxes?:number[][];
  located?:boolean;
  selection?:'none'|'checked'|'unchecked'|'unknown';
};

const distance=(a:number[],b:number[])=>Math.max(...a.map((v,i)=>Math.abs(v-b[i])));
const luminance=(rgb:number[])=>rgb.map(v=>{const c=v/255;return c<=.04045?c/12.92:((c+.055)/1.055)**2.4;})
  .reduce((sum,v,i)=>sum+v*[.2126,.7152,.0722][i],0);
function readableColor(foreground:number[],background:number[]):number[] {
  let color=[...foreground];const bg=luminance(background);
  for(let attempt=0;attempt<24;attempt++) {
    const fg=luminance(color),contrast=(Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05);
    if(contrast>=4.5)return color;
    color=color.map(v=>Math.round(bg>.35?v*.85:v+(255-v)*.15));
  }
  return bg>.35?[24,24,24]:[255,255,255];
}
function bounds(region:DocumentRegion,all:DocumentRegion[],source:Canvas,padding:number) {
  const b=region.box;
  let x=Math.max(0,Math.floor(b.x-padding)),y=Math.max(0,Math.floor(b.y-padding));
  let right=Math.min(source.width,Math.ceil(b.x+b.width+padding)),bottom=Math.min(source.height,Math.ceil(b.y+b.height+padding));
  for(const other of all)if(other!==region&&other.located!==false) {
    const o=other.box;
    if(Math.min(bottom,o.y+o.height)>Math.max(y,o.y)) {
      if(o.x+o.width<=b.x)x=Math.max(x,Math.ceil(o.x+o.width));
      if(o.x>=b.x+b.width)right=Math.min(right,Math.floor(o.x));
    }
    if(Math.min(right,o.x+o.width)>Math.max(x,o.x)) {
      if(o.y+o.height<=b.y)y=Math.max(y,Math.ceil(o.y+o.height));
      if(o.y>=b.y+b.height)bottom=Math.min(bottom,Math.floor(o.y));
    }
  }
  return {x,y,width:right-x,height:bottom-y};
}

function wrap(text:string,width:number,measure:(s:string)=>number):string[]|undefined {
  const lines:string[]=[];
  for(const paragraph of text.split('\n')) {
    let line='';
    const tokens=paragraph.match(/[A-Za-z0-9]+(?:[._/%+\-][A-Za-z0-9]+)*|\s+|./gu)??[];
    for(const token of tokens) {
      if(measure(token.trim())>width)return;
      if(line&&measure(line+token)>width){lines.push(line.trimEnd());line='';}
      line+=!line?token.trimStart():token;
    }
    if(line.trim())lines.push(line.trimEnd());
  }
  return lines.length?lines:undefined;
}

function squareOutline(ink:Uint8Array,stride:number,l:number,t:number,r:number,b:number) {
  const row=(y:number)=>{let n=0;for(let x=l;x<=r;x++)n+=ink[y*stride+x];return n/(r-l+1);};
  const col=(x:number)=>{let n=0;for(let y=t;y<=b;y++)n+=ink[y*stride+x];return n/(b-t+1);};
  const corners=[Math.max(row(t),row(t+1)),Math.max(row(b),row(b-1)),Math.max(col(l),col(l+1)),Math.max(col(r),col(r-1))];
  let empty=0;
  for(let y=t+2;y<=b-2;y++)for(let x=l+2;x<=r-2;x++)if(!ink[y*stride+x])empty++;
  return corners.every(fraction=>fraction>=.78)&&empty>=Math.max(1,(b-t-3)*(r-l-3)*.15);
}

export function renderDocumentLayout(source:Canvas,regions:DocumentRegion[]):Canvas {
  const output=createCanvas(source.width,source.height),ctx=output.getContext('2d'),original=source.getContext('2d');
  ctx.drawImage(source,0,0);
  for(const region of regions) {
    region.rendered=false;
    if(region.located===false){region.skipReason=region.skipReason||'layout-position';continue;}
    if(region.skipReason)continue;
    if(region.selection&&region.selection!=='none'){region.skipReason='layout-form-control';continue;}
    if(!region.translatedText?.trim()){region.skipReason='translation-incomplete';continue;}
    const b=region.box;
    if(regions.some(other=>other!==region&&other.located!==false&&Math.min(b.x+b.width,other.box.x+other.box.width)-Math.max(b.x,other.box.x)>2
      &&Math.min(b.y+b.height,other.box.y+other.box.height)-Math.max(b.y,other.box.y)>2)) {
      region.skipReason='layout-overlap';continue;
    }
    const lineHeights=region.lineBoxes?.map(box=>box[3]-box[1]).filter(h=>h>2).sort((a,b)=>a-b)??[];
    const sourceLines=Math.max(1,region.sourceText.split('\n').length);
    const nominal=region.fontSize??(lineHeights.length?lineHeights[Math.floor(lineHeights.length/2)]*.9:Math.min(38,b.height/sourceLines*.85));
    let done=false;
    for(const padding of [Math.max(3,Math.min(8,nominal*.3)),Math.max(6,Math.min(22,nominal*.8))]) {
      const rect=bounds(region,regions,source,padding),{x,y,width:w,height:h}=rect;
      if(w<4||h<5||w*h>12_000_000){region.skipReason='layout-space';break;}
      const pixels=original.getImageData(x,y,w,h),data=pixels.data;
      const bins=new Map<string,{n:number;sum:number[]}>();
      for(let p=0;p<w*h;p++) {
        const rgb=[data[p*4],data[p*4+1],data[p*4+2]],key=rgb.map(v=>v>>4).join(',');
        const bin=bins.get(key)??{n:0,sum:[0,0,0]};bin.n++;rgb.forEach((v,i)=>bin.sum[i]+=v);bins.set(key,bin);
      }
      const dominant=[...bins.values()].sort((a,b)=>b.n-a.n)[0],bg=dominant.sum.map(v=>Math.round(v/dominant.n));
      const ink=new Uint8Array(w*h),visited=new Uint8Array(w*h),erase=new Uint8Array(w*h),rules=new Uint8Array(w*h);
      let flat=0;
      for(let p=0;p<ink.length;p++) {
        const d=distance([data[p*4],data[p*4+1],data[p*4+2]],bg);
        if(d<30)flat++;if(d>32)ink[p]=1;
      }
      if(flat/ink.length<.6){region.skipReason='layout-background';break;}
      let unsafe=false,formControl=false,clipped=false,count=0;const fg=[0,0,0],foreground=new Map<string,{n:number;sum:number[]}>();
      for(let start=0;start<ink.length;start++) {
        if(!ink[start]||visited[start])continue;
        const component=[start];visited[start]=1;let l=w,t=h,r=0,bt=0,inside=0;
        for(let i=0;i<component.length;i++) {
          const p=component[i],px=p%w,py=Math.floor(p/w);
          l=Math.min(l,px);r=Math.max(r,px);t=Math.min(t,py);bt=Math.max(bt,py);
          if(x+px>=b.x&&x+px<b.x+b.width&&y+py>=b.y&&y+py<b.y+b.height)inside++;
          for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1],[1,1],[-1,-1],[1,-1],[-1,1]]) {
            const nx=px+dx,ny=py+dy,np=ny*w+nx;
            if(nx>=0&&nx<w&&ny>=0&&ny<h&&ink[np]&&!visited[np]){visited[np]=1;component.push(np);}
          }
        }
        const cw=r-l+1,ch=bt-t+1;
        // An outline at the start of a label may enclose a separate tick.
        // Keep the entire control and label if rewriting could erase either.
        if(inside&&ch>=6&&ch>=nominal*.42&&ch<=nominal*1.8&&cw/ch>=.74&&cw/ch<=1.35
          &&x+l<=b.x+nominal*.95&&r<w-1&&bt<h-1&&squareOutline(ink,w,l,t,r,bt)){
          formControl=true;break;
        }
        const rule=(cw>nominal*3&&ch<Math.max(3,nominal*.12)&&l===0&&r===w-1)||(ch>nominal*2&&cw<Math.max(3,nominal*.12));
        if(rule||!inside){for(const p of component)rules[p]=1;continue;}
        if(ch>nominal*2.2||(cw>nominal*9&&ch>nominal*1.5)){unsafe=true;break;}
        if(l===0||t===0||r===w-1||bt===h-1){clipped=true;continue;}
        for(const p of component){
          erase[p]=1;count++;const rgb=[data[p*4],data[p*4+1],data[p*4+2]],key=rgb.map(v=>v>>4).join(',');
          const bin=foreground.get(key)??{n:0,sum:[0,0,0]};bin.n++;rgb.forEach((v,i)=>bin.sum[i]+=v);foreground.set(key,bin);
          for(let c=0;c<3;c++)fg[c]+=data[p*4+c];
        }
      }
      if(formControl){region.skipReason='layout-form-control';break;}
      if(unsafe){region.skipReason='layout-artwork';break;}
      if(clipped){region.skipReason='layout-boundary';continue;}
      if(!count){region.skipReason='layout-no-ink';break;}
      let size=Math.max(9,nominal),lines:string[]|undefined,ascent=0,lineHeight=0;
      for(let attempt=0;attempt<36;attempt++) {
        ctx.font=`${region.kind==='heading'?'bold ':''}${size}px "RR Document Sans"`;
        lines=wrap(region.translatedText.trim(),w-2,text=>ctx.measureText(text).width);
        if(lines) {
          const measures=lines.map(line=>ctx.measureText(line));ascent=Math.max(...measures.map(m=>m.actualBoundingBoxAscent));
          const descent=Math.max(...measures.map(m=>m.actualBoundingBoxDescent));lineHeight=Math.max(size*1.2,ascent+descent+1);
          if(ascent+descent+(lines.length-1)*lineHeight<=h-2)break;
        }
        lines=undefined;size*=.94;
        if(size<Math.max(7,nominal*.55))break;
      }
      if(!lines){region.skipReason='layout-space';break;}
      const cleaned=ctx.getImageData(x,y,w,h),priorPixels=new Uint8ClampedArray(cleaned.data),radius=Math.max(3,Math.min(4,Math.round(nominal*.12)));
      for(let p=0;p<erase.length;p++)if(erase[p]) {
        const px=p%w,py=Math.floor(p/w);
        for(let dy=-radius;dy<=radius;dy++)for(let dx=-radius;dx<=radius;dx++) {
          const nx=px+dx,ny=py+dy,np=ny*w+nx;
          if(nx>=0&&nx<w&&ny>=0&&ny<h&&!rules[np])for(let c=0;c<3;c++)cleaned.data[np*4+c]=bg[c];
        }
      }
      ctx.putImageData(cleaned,x,y);ctx.save();ctx.beginPath();ctx.rect(x,y,w,h);ctx.clip();
      const dominantInk=[...foreground.values()].sort((a,b)=>b.n-a.n)[0];
      // Colored antialias fringes around black glyphs are not colored ink.
      const neutral=[...foreground.values()].filter(bin=>{
        const rgb=bin.sum.map(v=>v/bin.n);return Math.max(...rgb)-Math.min(...rgb)<18&&Math.max(...rgb)<100;
      });
      const neutralCount=neutral.reduce((sum,bin)=>sum+bin.n,0);
      const core=neutral.sort((a,b)=>b.n-a.n)[0];
      const selected=core&&neutralCount>count*.18?core:dominantInk;
      const measured=selected?selected.sum.map(v=>Math.round(v/selected.n)):fg.map(v=>Math.round(v/count));
      ctx.fillStyle=`rgb(${readableColor(measured,bg).join(',')})`;ctx.textBaseline='alphabetic';
      const top=y+Math.max(1,(h-(lines.length-1)*lineHeight-size)/2);
      lines.forEach((line,i)=>ctx.fillText(line,x+1+Math.max(0,ctx.measureText(line).actualBoundingBoxLeft),top+ascent+i*lineHeight));
      ctx.restore();
      const painted=ctx.getImageData(x,y,w,h);
      // Reject new glyphs that run into a figure or a neighbouring text row.
      // Restoring outline pixels alone would still leave Chinese drawn inside
      // the figure's otherwise blank interior.
      let collision=false;
      const clearance=Math.max(1,Math.min(7,Math.round(size*.22)));
      for(let p=0;p<rules.length&&!collision;p++)if(rules[p]) {
        const px=p%w,py=Math.floor(p/w);
        for(let dy=-clearance;dy<=clearance&&!collision;dy++)for(let dx=-clearance;dx<=clearance;dx++) {
          const nx=px+dx,ny=py+dy,np=ny*w+nx;
          if(nx<0||nx>=w||ny<0||ny>=h||erase[np])continue;
          const changed=[0,1,2].some(c=>Math.abs(painted.data[np*4+c]-cleaned.data[np*4+c])>25);
          if(changed){collision=true;break;}
        }
      }
      if(collision){
        cleaned.data.set(priorPixels);ctx.putImageData(cleaned,x,y);
        region.skipReason='layout-artwork';break;
      }
      // A neighbour's original glyph is not artwork to restore: its translated
      // pixels may already occupy this padding. Preserve the current output.
      for(let p=0;p<rules.length;p++)if(rules[p])for(let c=0;c<4;c++)painted.data[p*4+c]=priorPixels[p*4+c];
      ctx.putImageData(painted,x,y);
      region.rendered=true;region.skipReason=undefined;Object.assign(region,{renderBox:rect});done=true;break;
    }
    if(!done&&!region.skipReason)region.skipReason='layout-space';
  }
  return output;
}

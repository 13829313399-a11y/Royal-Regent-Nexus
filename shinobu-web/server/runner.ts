/** Private stdio worker. Only the Python worker supplies paths and translations. */
import { readFile, writeFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { createCanvas, loadImage, registerFont, Image, ImageData, type Canvas } from 'canvas';
import { type PipelinePlatform, type PipelineConfig } from '@shinobu/image-pipeline';
import { createNodeModelRuntime } from '@shinobu/model-runtime/node';
import { runPipeline } from '../packages/image-pipeline/src/pipeline/orchestrator';
import { disposePipelineArtifacts } from '../packages/image-pipeline/src/pipeline/resources';
import { prepareRegions, renderDocument, splitRuledRegion, splitMixedWords, preserveReason, registerDocumentFont, type Region } from './documentTypeset';
import { runOcr } from '../packages/image-pipeline/src/pipeline/ocr';
import type { TextRegion } from '../packages/image-pipeline/src/types';
import type { PipelineImage } from '../packages/image-pipeline/src/runtime/platform';

// Upstream image decoding uses FileReader. Supply the one operation needed in Node.
class NodeFileReader {
  result: string | null = null;
  onload?: () => void;
  onerror?: () => void;
  readAsDataURL(blob: Blob) {
    void blob.arrayBuffer().then(bytes => {
      this.result = `data:${blob.type};base64,${Buffer.from(bytes).toString('base64')}`;
      this.onload?.();
    }, () => this.onerror?.());
  }
}
Object.assign(globalThis, { FileReader: NodeFileReader });
// Pipeline diagnostic output must never become protocol messages or disclose text.
console.log = console.info = console.debug = console.warn = () => undefined;
let writes = Promise.resolve();
const send = (value: unknown) => {
  const line = `${JSON.stringify(value)}\n`;
  writes = writes.then(() => new Promise<void>((resolveWrite, rejectWrite) => {
    process.stdout.write(line, error => error ? rejectWrite(error) : resolveWrite());
  }));
  return writes;
};
const lines = createInterface({ input: process.stdin, crlfDelay: Infinity })[Symbol.asyncIterator]();
async function receive() {
  const line = await lines.next();
  if (line.done) throw new Error('Worker disconnected');
  return JSON.parse(line.value);
}
const platform = {
  createCanvas, createImage: () => new Image(), loadImage,
  createImageData: (width: number, height: number) => new ImageData(width, height),
  registerFont: (path: string, family: string) => registerFont(path, { family, weight: 'bold' }),
  waitForFonts: async () => undefined,
  encodeCanvasToPng: (canvas: unknown) => new Blob([new Uint8Array((canvas as Canvas).toBuffer('image/png'))]),
} as unknown as PipelinePlatform;

async function main() {
  const init = await receive();
  const modelRuntime = createNodeModelRuntime({ manifestRoot: import.meta.dirname, modelRoot: init.modelRoot });
  // Server CPU is predictable and avoids implicitly trying unavailable CUDA drivers.
  const runtime = { ...modelRuntime, getSession: (name: Parameters<typeof modelRuntime.getSession>[0]) => modelRuntime.getSession(name, ['cpu']) };
  registerDocumentFont(import.meta.dirname);
  const config: PipelineConfig = { sourceLang: init.direction === 'zh_to_en' ? 'zh-CN' : 'en',
    targetLang: init.direction === 'zh_to_en' ? 'en' : 'zh-CN', translator: 'llm',
    llmProvider: 'custom', llmAuthMode: 'api_key', llmBaseUrl: '', llmModel: '',
    typesetDebug: false, eraseDebug: false, collectDebugLog: false, ocrEngine: 'paddleocr_v6_medium',
    ocrPostFilter: 'off', processMode: 'translate' };
  try {
    for (const [index, page] of init.pages.entries()) {
      const bytes = await readFile(page.input);
      const decoded=await loadImage(bytes), original=createCanvas(decoded.width,decoded.height);
      original.getContext('2d').drawImage(decoded,0,0);
      let recognized: Region[];
      if (Array.isArray(page.nativeRegions) && page.nativeRegions.length) {
        recognized = page.nativeRegions;
        for(const [areaIndex,area] of (page.rasterAreas??[]).entries()) {
          const crop=createCanvas(Math.max(1,Math.ceil(area.width)),Math.max(1,Math.ceil(area.height)));
          crop.getContext('2d').drawImage(decoded,-area.x,-area.y);
          const result=await runPipeline(new File([new Uint8Array(crop.toBuffer('image/png'))],'embedded.png',{type:'image/png'}),config,
            value=>{void send({event:'progress',stage:value.stage,page:index});},
            {platform,modelRuntime:runtime,detectionFallbackStrategy:{kind:'heuristic-only'},stopAfter:'order',smallTextEnhance:{documentMode:true}});
          recognized=recognized.concat(result.stageRegions.ocr.map(region=>({...region,id:`embedded-${areaIndex}-${region.id}`,
            box:{...region.box,x:region.box.x+area.x,y:region.box.y+area.y}})));
          disposePipelineArtifacts(result);crop.width=crop.height=1;
        }
      } else {
        const result = await runPipeline(new File([new Uint8Array(bytes)], 'page.png', {type:'image/png'}), config,
          value => { void send({ event:'progress',stage:value.stage,page:index }); },
          { platform, modelRuntime:runtime, detectionFallbackStrategy:{kind:'heuristic-only'},
            stopAfter:'order',smallTextEnhance:{documentMode:true} });
        // Deliberately use pre-merge OCR lines: manga reading-order/bubble groups
        // can combine different columns and paint over engineering drawings.
        recognized = result.stageRegions.ocr.map(region => ({...region,box:{...region.box}}));
        disposePipelineArtifacts(result);
        const split=recognized.flatMap(region=>splitRuledRegion(original,region));
        const cells=split.filter(r=>r.sourceText==='');
        if(cells.length) {
          const corrected=await runOcr(decoded as unknown as PipelineImage,cells as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
          recognized=[...split.filter(r=>r.sourceText!==''),...corrected.regions];
        }
        const groups=recognized.map(parent=>({parent,parts:splitMixedWords(original,parent)})).filter(group=>group.parts.length>1);
        if(groups.length) {
          const words=await runOcr(decoded as unknown as PipelineImage,groups.flatMap(g=>g.parts) as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
          const byId=new Map(words.regions.map(r=>[r.id,r]));
          const normalize=(s:string)=>s.toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]/g,'');
          for(const group of groups) {
            const parts=group.parts.map(p=>byId.get(p.id));
            if(parts.some(p=>!p||(p.prob??0)<.90)||normalize(parts.map(p=>p!.sourceText).join(' '))!==normalize(group.parent.sourceText))continue;
            const merged:Region[]=[];
            for(const part of parts as Region[]) {
              const previous=merged[merged.length-1];
              if(previous&&!preserveReason(previous,init.direction)&&!preserveReason(part,init.direction)) {
                previous.sourceText+=' '+part.sourceText;
                previous.box.width=part.box.x+part.box.width-previous.box.x;
              } else merged.push({...part,box:{...part.box}});
            }
            recognized=recognized.filter(r=>r!==group.parent).concat(merged);
          }
        }
      }
      const regions=prepareRegions(recognized,init.direction);
      const targets=regions.filter(region=>!region.skipReason);
      if(targets.length) {
        await send({event:'translate',texts:targets.map(region=>region.sourceText)});
        const reply=await receive();
        if(!Array.isArray(reply.translations)||reply.translations.length!==targets.length||reply.translations.some((v:unknown)=>typeof v!=='string')) throw new Error('Invalid translation response');
        targets.forEach((region,i)=>region.translatedText=reply.translations[i]);
      }
      const output=renderDocument(original,regions);
      await writeFile(page.output,output.toBuffer('image/png'));
      await send({event:'page',index,status:regions.some(r=>r.rendered)?'completed':'no-translatable-text',
        record:{translations:regions,policy:'document-safe-v1'}});
      original.width=original.height=output.width=output.height=1;
    }
    await send({ event: 'done' });
  } finally {
    await modelRuntime.dispose();
  }
}
const execution = process.argv.includes('--check') ? import('onnxruntime-node').then(() => undefined) : main();
void execution.then(async () => { await writes; process.exit(0); }, async () => {
  try { await send({ event: 'error' }); } finally { process.exit(1); }
});

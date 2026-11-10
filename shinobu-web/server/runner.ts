/** Private stdio worker. Only the Python worker supplies paths and translations. */
import { readFile, writeFile } from 'node:fs/promises';
import { createInterface } from 'node:readline';
import { availableParallelism } from 'node:os';
import { createCanvas, loadImage, registerFont, Image, ImageData, type Canvas } from 'canvas';
import { type PipelinePlatform, type PipelineConfig } from '@shinobu/image-pipeline';
import { createNodeModelRuntime } from '@shinobu/model-runtime/node';
import { runPipeline } from '../packages/image-pipeline/src/pipeline/orchestrator';
import { disposePipelineArtifacts } from '../packages/image-pipeline/src/pipeline/resources';
import { prepareRegions, renderDocument, uncoveredOcrRegions, uncoveredOcrCandidates, splitRuledRegion, fragmentedCaptionGroups, verifiedCaptionMerge, splitMixedWords, verifiedWordParts, documentWordCrops, documentOcrRetry, acceptDocumentOcrRetry, preserveReason, overlap, registerDocumentFont, type Region } from './documentTypeset';
import { runOcr } from '../packages/image-pipeline/src/pipeline/ocr';
import { detectSmallTextRegions } from '../packages/image-pipeline/src/pipeline/detect/smallTextDetect';
import { detectTextRegionsWithMask } from '../packages/image-pipeline/src/pipeline/detect';
import type { TextRegion } from '../packages/image-pipeline/src/types';
import type { PipelineImage } from '../packages/image-pipeline/src/runtime/platform';
import {renderDocumentLayout, type DocumentRegion} from './documentLayout';

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
  if(init.mode==='render-layout') {
    registerDocumentFont(import.meta.dirname);
    for(const [index,page] of init.pages.entries()) {
      const decoded=await loadImage(await readFile(page.input)),source=createCanvas(decoded.width,decoded.height);
      source.getContext('2d').drawImage(decoded,0,0);
      const regions:DocumentRegion[]=page.regions;
      const output=renderDocumentLayout(source,regions);
      await writeFile(page.output,output.toBuffer('image/png'));
      await send({event:'page',index,status:regions.some(r=>r.rendered)?'completed':regions.length?'no-rendered-text':'no-translatable-text',
        record:{translations:regions,policy:'document-layout-v2'}});
      source.width=source.height=output.width=output.height=1;
    }
    await send({event:'done'});return;
  }
  const modelRuntime = createNodeModelRuntime({ manifestRoot: import.meta.dirname, modelRoot: init.modelRoot,
    cpuThreads: Math.max(1, Math.min(4, Math.floor(availableParallelism()/2))) });
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
      const native:Region[]=Array.isArray(page.nativeRegions)?page.nativeRegions:[];
      let detected:TextRegion[];
      if (native.length) {
        // A PDF can mix real text, outlined letters and tiny caption images.
        // Detect across the whole page, but OCR only areas not owned by native
        // text. This also avoids recognizing/translating the same value twice.
        await send({event:'progress',stage:'detect',page:index});
        const result=await detectTextRegionsWithMask(decoded as unknown as PipelineImage,platform,runtime,
          {kind:'heuristic-only'},{smallTextEnhance:{documentMode:true}});
        detected=uncoveredOcrCandidates(result.regions,native);
        if(result.rawMaskCanvas)result.rawMaskCanvas.width=result.rawMaskCanvas.height=1;
        await send({event:'progress',stage:'ocr',page:index});
        recognized=detected.length?(await runOcr(decoded as unknown as PipelineImage,detected,'paddleocr_v6_medium',platform,{},runtime)).regions:[];
      } else {
        const result = await runPipeline(new File([new Uint8Array(bytes)], 'page.png', {type:'image/png'}), config,
          value => { void send({ event:'progress',stage:value.stage,page:index }); },
          { platform, modelRuntime:runtime, detectionFallbackStrategy:{kind:'heuristic-only'},
            stopAfter:'order',smallTextEnhance:{documentMode:true} });
        // Deliberately use pre-merge OCR lines: manga reading-order/bubble groups
        // can combine different columns and paint over engineering drawings.
        recognized = result.stageRegions.ocr.map(region => ({...region,box:{...region.box}}));
        detected=result.stageRegions.detected;
        disposePipelineArtifacts(result);
      }
      // Model boxes around a silhouette can suppress a small caption inside
      // it. Keep independently verified stroke candidates for color recovery.
      const strokes=detectSmallTextRegions(decoded as unknown as PipelineImage,platform,{documentMode:true});
      const unread=uncoveredOcrCandidates([...strokes.regions,...detected],native).filter(r=>!recognized.some(other=>/[A-Za-z]{2}/.test(other.sourceText)&&(other.prob??0)>=.9&&
        overlap(r.box,other.box)/Math.min(r.box.width*r.box.height,other.box.width*other.box.height)>.5))
        .filter((r,i,all)=>!all.slice(0,i).some(other=>overlap(r.box,other.box)/Math.min(r.box.width*r.box.height,other.box.width*other.box.height)>.8))
        .map(r=>({...r,sourceText:'',box:{...r.box}}));
      const split=recognized.flatMap(region=>splitRuledRegion(original,region));
      const cells=split.filter(r=>r.sourceText==='');
      if(cells.length) {
        const corrected=await runOcr(decoded as unknown as PipelineImage,cells as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
        recognized=[...split.filter(r=>r.sourceText!==''),...corrected.regions];
      }
      const retry=documentOcrRetry(original,[...native,...recognized,...unread]);
      let contrast=decoded;
      if(retry.regions.length) {
        contrast=await loadImage(retry.canvas.toBuffer('image/png'));
        const corrected=await runOcr(contrast as unknown as PipelineImage,retry.regions as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
        const byId=new Map(corrected.regions.map(r=>[r.id,r]));
        recognized=recognized.map(parent=>{
          const found=byId.get(`${parent.id}-contrast`);
          return acceptDocumentOcrRetry(parent,found)?{...parent,sourceText:found!.sourceText,prob:found!.prob}:parent;
        });
        for(const parent of unread) {
          const candidate=retry.regions.find(r=>r.id===`${parent.id}-contrast`),found=byId.get(`${parent.id}-contrast`);
          if(candidate&&acceptDocumentOcrRetry(parent,found))recognized.push({...parent,sourceText:found!.sourceText,prob:found!.prob,fgColor:candidate.fgColor});
        }
      }
      retry.canvas.width=retry.canvas.height=1;
      const fragments=fragmentedCaptionGroups(recognized);
      if(fragments.length) {
        const corrected=await runOcr(decoded as unknown as PipelineImage,fragments.map(g=>g.candidate) as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
        const byId=new Map(corrected.regions.map(r=>[r.id,r]));
        for(const group of fragments) {
          const found=byId.get(group.candidate.id);
          if(verifiedCaptionMerge(group.parents,found))recognized=recognized.filter(r=>!group.parents.includes(r)).concat({...found!,box:{...group.candidate.box}});
        }
      }
      const groups=recognized.map(parent=>({parent,parts:splitMixedWords(original,parent)})).filter(group=>group.parts.length>1);
      if(groups.length) {
        const wordCrops=groups.flatMap(g=>documentWordCrops(original,g.parts,[...native,...recognized.filter(r=>r!==g.parent)]));
        const tight=await runOcr(decoded as unknown as PipelineImage,groups.flatMap(g=>g.parts) as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
        const words=await runOcr(decoded as unknown as PipelineImage,wordCrops as TextRegion[],'paddleocr_v6_medium',platform,{},runtime);
        const byId=new Map(tight.regions.map(r=>[r.id,r]));
        const parentById=new Map(groups.flatMap(g=>g.parts.map(p=>[p.id,g.parent] as const)));
        for(const word of words.regions) {
          const previous=byId.get(word.id);
          const normalize=(s:string)=>s.toLowerCase().replace(/[^a-z0-9\u3400-\u9fff]/g,'');
          const agrees=normalize(parentById.get(word.id)!.sourceText).includes(normalize(word.sourceText));
          if(!previous||(previous.prob??0)<.90||(/[A-Za-z]/.test(word.sourceText)&&(word.prob??0)>=(agrees?.90:.97)))byId.set(word.id,word);
        }
        for(const group of groups) {
          const parts=verifiedWordParts(original,group.parent,group.parts,byId);
          if(!parts)continue;
          const merged:Region[]=[];
          for(const part of parts as Region[]) {
            const previous=merged[merged.length-1];
            if(previous&&!/^Cut$/i.test(part.sourceText.trim())&&!preserveReason(previous,init.direction)&&!preserveReason(part,init.direction)) {
              previous.sourceText+=' '+part.sourceText;
              previous.box.width=part.box.x+part.box.width-previous.box.x;
            } else merged.push({...part,box:{...part.box}});
          }
          recognized=recognized.filter(r=>r!==group.parent).concat(merged);
        }
      }
      const regions=prepareRegions([...native,...uncoveredOcrRegions(recognized,native)],init.direction,original);
      const targets=regions.filter(region=>!region.skipReason);
      if(targets.length) {
        await send({event:'translate',texts:targets.map(region=>region.sourceText)});
        const reply=await receive();
        if(!Array.isArray(reply.translations)||reply.translations.length!==targets.length||reply.translations.some((v:unknown)=>typeof v!=='string')) throw new Error('Invalid translation response');
        targets.forEach((region,i)=>region.translatedText=reply.translations[i]);
      }
      const output=renderDocument(original,regions);
      await writeFile(page.output,output.toBuffer('image/png'));
      await send({event:'page',index,status:regions.some(r=>r.rendered)?'completed':regions.length?'no-rendered-text':'no-translatable-text',
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

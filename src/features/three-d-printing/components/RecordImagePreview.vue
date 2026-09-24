<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { ZoomIn, ZoomOut, Maximize } from '@lucide/vue';
import LegacyDialog from './LegacyDialog.vue';

const props = defineProps<{ src: string; open: boolean }>();
const emit = defineEmits<{ close: []; 'after-close': [] }>();
const zoom = ref(1);
const canvas = ref<HTMLDivElement>();
watch(() => props.open, async open => {
  if (!open) return;
  zoom.value = 1;
  await nextTick();
  if (canvas.value) { canvas.value.scrollLeft = 0; canvas.value.scrollTop = 0; }
});
async function setZoom(value: number) {
  const viewport = canvas.value;
  const ratio = value / zoom.value;
  const centerX = (viewport?.scrollLeft || 0) + (viewport?.clientWidth || 0) / 2;
  const centerY = (viewport?.scrollTop || 0) + (viewport?.clientHeight || 0) / 2;
  zoom.value = value;
  await nextTick();
  if (viewport) {
    viewport.scrollLeft = value === 1 ? 0 : centerX * ratio - viewport.clientWidth / 2;
    viewport.scrollTop = value === 1 ? 0 : centerY * ratio - viewport.clientHeight / 2;
  }
}
</script>

<template>
  <Teleport to="body">
    <LegacyDialog :open="open" title="图片详情" class="record-image-viewer" @close="emit('close')" @after-close="emit('after-close')">
      <div class="image-viewer-toolbar" role="group" aria-label="图片缩放">
        <button type="button" :disabled="zoom <= 1" @click="setZoom(zoom - 0.5)"><ZoomOut :size="16" />缩小</button>
        <output aria-live="polite">{{ Math.round(zoom * 100) }}%</output>
        <button type="button" :disabled="zoom >= 4" @click="setZoom(zoom + 0.5)"><ZoomIn :size="16" />放大</button>
        <button type="button" @click="setZoom(1)"><Maximize :size="16" />适应窗口</button>
      </div>
      <div ref="canvas" class="image-viewer-canvas" tabindex="0" aria-label="图片细节，可滚动查看">
        <div class="image-viewer-size" :style="{ width: `${zoom * 100}%`, height: `${zoom * 100}%` }">
          <img :src="src" alt="记录图片大图" />
        </div>
      </div>
      <p class="image-viewer-hint">放大后可滚动查看细节 · Esc 关闭预览，继续编辑记录</p>
    </LegacyDialog>
  </Teleport>
</template>

<style>
.record-image-viewer.legacy-dialog { width:min(1200px,96vw); max-height:94dvh; }
.record-image-viewer > .legacy-dialog-body { padding:0; }
.image-viewer-toolbar { display:flex; align-items:center; justify-content:center; flex-wrap:wrap; gap:12px; padding:12px; border-bottom:1px solid var(--border); }
.image-viewer-toolbar button { display:inline-flex; align-items:center; gap:6px; padding:7px 10px; border:1px solid var(--border); border-radius:8px; color:var(--primary); background:var(--card); font-size:13px; }
.image-viewer-toolbar button:disabled { opacity:.4; cursor:default; }
.image-viewer-toolbar button:focus-visible, .image-viewer-canvas:focus-visible { outline:2px solid var(--ring); outline-offset:-2px; }
.image-viewer-toolbar output { min-width:44px; text-align:center; font-size:13px; color:var(--muted-foreground); }
.image-viewer-canvas { height:calc(94dvh - 180px); min-height:160px; overflow:auto; background:var(--muted); }
.image-viewer-size { display:flex; align-items:center; justify-content:center; }
.image-viewer-size img { width:100%; height:100%; max-width:none; object-fit:contain; }
.image-viewer-hint { padding:10px 14px; margin:0; text-align:center; font-size:12px; color:var(--muted-foreground); }
@media(max-width:500px) { .image-viewer-toolbar { gap:5px; } .image-viewer-toolbar button { padding:7px; } }
</style>

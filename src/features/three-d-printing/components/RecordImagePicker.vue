<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ImagePlus, Upload, X, ZoomIn } from '@lucide/vue';
import RecordImagePreview from './RecordImagePreview.vue';
const props = defineProps<{ modelValue: File | null; existingUrl: string; allowed: boolean; disabled: boolean; inherited?: boolean }>();
const emit = defineEmits<{ 'update:modelValue': [file: File | null] }>();
const input = ref<HTMLInputElement>();
const preview = ref('');
const error = ref('');
const dragging = ref(false);
const previewOpen = ref(false);
const displayedImage = computed(() => preview.value || props.existingUrl);
watch(() => props.modelValue, (file, _, cleanup) => {
  preview.value = file ? URL.createObjectURL(file) : '';
  const url = preview.value;
  cleanup(() => { if (url) URL.revokeObjectURL(url); });
}, { immediate: true });
function choose(file?: File | null) {
  if (!file || !props.allowed || props.disabled) return;
  error.value = '';
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    error.value = '请选择 JPEG、PNG 或 WebP 图片。'; return;
  }
  if (file.size > 5 * 1024 * 1024) {
    error.value = '图片超过 5MB，请缩小后再上传。'; return;
  }
  emit('update:modelValue', file);
}
function pasteImage(event: ClipboardEvent) {
  if (!props.allowed || props.disabled) return;
  const file = Array.from(event.clipboardData?.items || []).find(item => item.kind === 'file' && item.type.startsWith('image/'))?.getAsFile();
  if (!file) return;
  event.preventDefault(); choose(file);
}
function select(event: Event) {
  const el = event.target as HTMLInputElement;
  choose(el.files?.[0]); el.value = '';
}
function drop(event: DragEvent) {
  dragging.value = false;
  choose(event.dataTransfer?.files?.[0]);
}
defineExpose({ pasteImage });
</script>

<template>
  <section class="record-photo" aria-label="记录图片">
    <div class="photo-heading"><h3>记录图片</h3><span v-if="modelValue">待保存</span><span v-else-if="existingUrl">{{ inherited ? '产品参考图' : '已保存' }}</span></div>
    <button class="photo-zone" :class="{ dragging, 'has-photo': displayedImage }" type="button" :aria-label="displayedImage ? '放大查看记录图片' : '记录图片粘贴区'"
      :disabled="!displayedImage && (!allowed || disabled)" @click="displayedImage ? previewOpen = true : input?.click()"
      @dragover.prevent="dragging = allowed && !disabled" @dragleave="dragging = false" @drop.prevent="drop">
      <img v-if="displayedImage" :src="displayedImage" alt="记录图片预览" />
      <template v-else><ImagePlus :size="30" /><strong>{{ allowed ? '粘贴一张现场图片' : '暂无图片' }}</strong><span v-if="allowed">Ctrl + V 粘贴 · 拖入或选择图片</span></template>
    </button>
    <input ref="input" class="photo-input" type="file" accept="image/jpeg,image/png,image/webp" aria-label="选择记录图片" :disabled="!allowed || disabled" @change="select" />
    <div class="photo-actions">
      <button v-if="displayedImage" type="button" @click="previewOpen = true"><ZoomIn :size="14" />放大查看</button>
      <button v-if="allowed" type="button" :disabled="disabled" @click="input?.click()"><Upload :size="14" />{{ displayedImage ? '更换图片' : '选择图片' }}</button>
      <button v-if="allowed && modelValue" type="button" :disabled="disabled" @click="emit('update:modelValue', null); error = ''"><X :size="14" />取消本次图片</button>
    </div>
    <p v-if="error" class="photo-error" role="alert">{{ error }}</p>
    <p v-else>{{ allowed ? '在窗口任意位置粘贴，保存记录时上传。' : '当前账号无图片上传权限。' }}</p>
    <small>仅用于本条记录 · PNG / JPG / WebP · 最大 5MB</small>
    <RecordImagePreview v-if="previewOpen && displayedImage" :src="displayedImage" @close="previewOpen = false" />
  </section>
</template>

<style scoped>
.record-photo { padding: 18px; border: 1px solid var(--border); border-radius: 14px; background: var(--card); min-width: 0; }
.photo-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:14px; }
h3 { font-size:14px; font-weight:650; color:var(--foreground); }
.photo-heading span { font-size:11px; color:var(--primary); background:var(--accent); padding:3px 7px; border-radius:5px; }
.photo-zone { width:100%; min-height:190px; aspect-ratio: 1.35; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; overflow:hidden; border:1px dashed color-mix(in oklch,var(--primary) 35%,var(--border)); border-radius:10px; color:var(--primary); background:var(--background); }
.photo-zone img { display:block; width:100%; height:100%; max-height:250px; object-fit:contain; }
.photo-zone strong { font-size:14px; font-weight:600; }
.photo-zone span, p, small { font-size:12px; line-height:1.7; color:var(--muted-foreground); }
.photo-zone:hover:not(:disabled), .dragging { background:var(--accent); border-color:var(--primary); }
.photo-zone:focus-visible { outline:2px solid var(--ring); outline-offset:3px; }
.photo-zone.has-photo { cursor:zoom-in; }
.photo-input { display:none; }
.photo-actions { display:flex; gap:14px; flex-wrap:wrap; margin:12px 0; }
.photo-actions button { display:inline-flex; align-items:center; gap:5px; font-size:12px; font-weight:600; color:var(--primary); }
button:disabled { cursor:default; opacity:.7; }
.photo-error { color:var(--destructive); }
p { margin-top:10px; }
small { display:block; font-size:11px; }
</style>

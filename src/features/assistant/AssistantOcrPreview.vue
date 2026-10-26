<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { assistantApi } from './api'
import { documentLocation, type DocumentSegment } from './documentFormat'
import { getAuthenticationGeneration } from '@/lib/authenticationGeneration'

const props = defineProps<{ id: string; parts: DocumentSegment[] }>()
const regions = computed(() => props.parts.filter(p => p.locator.kind === 'ocr_region'))
const selected = ref(0), url = ref(''), error = ref(''), loading = ref(false), valid = ref(true), zoomed = ref(false)
const part = computed(() => regions.value[selected.value])
const locator = computed(() => part.value?.locator.kind === 'ocr_region' ? part.value.locator : null)
const boxStyle = computed(() => {
  const box = locator.value?.bbox
  return box ? { left: `${box.x * 100}%`, top: `${box.y * 100}%`, width: `${box.width * 100}%`, height: `${box.height * 100}%` } : {}
})
let generation = 0
function clear() { generation++; if (url.value) URL.revokeObjectURL(url.value); url.value = ''; error.value = ''; loading.value = false }
function invalidate() { clear(); valid.value = false }
function imageFailed() { clear(); error.value = '原页图片未能显示，请重试' }
async function load() {
  clear()
  if (!valid.value || !locator.value) return
  const ticket = generation, identity = getAuthenticationGeneration()
  loading.value = true
  try {
    const version = part.value?.document_version
    const blob = await (version ? assistantApi.documentPage(props.id, locator.value.page, version) : assistantApi.documentPage(props.id, locator.value.page))
    if (ticket !== generation || identity !== getAuthenticationGeneration()) return
    url.value = URL.createObjectURL(blob)
  } catch (reason) {
    if (ticket === generation && identity === getAuthenticationGeneration()) error.value = reason instanceof Error ? reason.message : '原页暂不可用'
  } finally { if (ticket === generation) loading.value = false }
}
watch(() => [props.id, props.parts], () => { valid.value = true; selected.value = 0; zoomed.value = false; void load() }, { immediate: true, flush: 'sync' })
watch(selected, () => { void load() })
onMounted(() => window.addEventListener('auth-session-boundary-changed', invalidate))
onBeforeUnmount(() => { invalidate(); window.removeEventListener('auth-session-boundary-changed', invalidate) })
</script>
<template>
  <section v-if="valid && locator && part" class="yl-ocr-preview" aria-label="扫描原页与识别区域">
    <label v-if="regions.length > 1">查看位置 <select v-model="selected" aria-label="识别区域"><option v-for="(region, index) in regions" :key="index" :value="index">{{ documentLocation(region.locator) }}</option></select></label>
    <strong>{{ documentLocation(locator) }}</strong>
    <p>图像识别候选 · 待核对。评分不是正确率，模糊字符与数值不能推定。</p>
    <p class="yl-ocr-candidate">{{ part.text }}</p>
    <small v-if="part.metadata?.signal_score != null">识别评分 {{ part.metadata.signal_score.toFixed(3) }}</small>
    <p v-if="loading" role="status">正在读取原页…</p>
    <div v-if="url"><button type="button" :aria-pressed="zoomed" @click="zoomed = !zoomed">{{ zoomed ? '适应宽度' : '放大原页' }}</button><div class="yl-ocr-scroll" tabindex="0" aria-label="原页预览，可滚动查看"><div class="yl-ocr-page" :class="{ 'yl-ocr-zoomed': zoomed }"><img :key="url" :src="url" :alt="`第 ${locator.page} 页原页预览（识别分辨率）`" @error="imageFailed"/><span class="yl-ocr-box" :style="boxStyle" aria-hidden="true"/></div></div><small>原页预览使用识别分辨率；框内为当前候选区域。</small></div>
    <div v-if="error"><p role="status">{{ error }}</p><button type="button" @click="load">重试读取原页</button></div>
  </section>
</template>
<style scoped>
.yl-ocr-preview{display:grid;grid-template-columns:minmax(0,1fr);gap:8px;min-width:0;margin:12px 0;padding:12px;border:1px solid var(--yl-line);border-radius:12px;background:var(--yl-panel)}
.yl-ocr-preview>div{min-width:0}
.yl-ocr-preview p{margin:0;overflow-wrap:anywhere}.yl-ocr-preview select{max-width:100%;border:1px solid var(--yl-line);background:var(--yl-paper);border-radius:6px;padding:4px}.yl-ocr-candidate{font-weight:600;white-space:pre-wrap}.yl-ocr-scroll{max-width:100%;max-height:420px;overflow:auto;margin-top:8px;background:white;border:1px solid var(--yl-line)}.yl-ocr-scroll:focus-visible{outline:2px solid var(--yl-jade);outline-offset:2px}.yl-ocr-page{position:relative;width:100%;line-height:0}.yl-ocr-page.yl-ocr-zoomed{width:1000px;max-width:none}.yl-ocr-page img{display:block;width:100%;max-width:none;height:auto}.yl-ocr-box{position:absolute;border:2px solid var(--yl-jade);background:#0c857815;pointer-events:none}
</style>

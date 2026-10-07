<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { DialogRoot, DialogPortal, DialogOverlay, DialogContent, DialogTitle, DialogDescription } from 'reka-ui'
import { countdownText, parseDeploymentNotice, type DeploymentNotice } from '@/lib/deploymentNotice'

const notice = ref<DeploymentNotice | null>(null)
const now = ref(Date.now())
const offset = ref(0)
const acknowledged = ref('')
const dismissed = ref('')
const connected = ref(true)
let pollTimer: ReturnType<typeof setTimeout> | undefined
let tickTimer: ReturnType<typeof setInterval> | undefined
let controller: AbortController | undefined
let stopped = false
const phase = computed(() => notice.value?.phase)
const key = computed(() => `${notice.value?.id}:${phase.value}`)
const visible = computed(() => !!notice.value && dismissed.value !== key.value
  && (notice.value.expiresAt === undefined || now.value < notice.value.expiresAt))
const modalOpen = computed(() => visible.value && (phase.value === 'maintenance' || acknowledged.value !== key.value))
const remaining = computed(() => Math.max(0, Math.ceil(((notice.value?.startsAt ?? now.value) - now.value) / 1000)))
const title = computed(() => phase.value === 'scheduled' ? '系统更新停机提醒'
  : phase.value === 'maintenance' ? '系统正在维护' : phase.value === 'completed' ? '系统已恢复' : '更新已取消')
function acknowledge() { if (phase.value !== 'maintenance') acknowledged.value = key.value }
function dismiss() { dismissed.value = key.value }
function refresh() { window.location.reload() }
async function poll() {
  if (stopped || controller) return
  controller = new AbortController()
  const timeout = setTimeout(() => controller?.abort(), 5000)
  try {
    const response = await fetch('/deployment-status.json', { cache: 'no-store', credentials: 'omit', signal: controller.signal })
    if (!response.ok) throw new Error('Notice unavailable')
    const next = parseDeploymentNotice(await response.json())
    if (next && !stopped) {
      const serverTime = Date.parse(response.headers.get('Date') ?? '')
      if (Number.isFinite(serverTime)) offset.value = serverTime - Date.now()
      now.value = Date.now() + offset.value
      notice.value = next
      connected.value = true
    }
  } catch { connected.value = false } finally {
    clearTimeout(timeout)
    controller = undefined
    if (!stopped) pollTimer = setTimeout(poll, 10000)
  }
}
function resume() {
  if (document.visibilityState === 'visible') { clearTimeout(pollTimer); void poll() }
}
onMounted(() => {
  void poll()
  tickTimer = setInterval(() => { now.value = Date.now() + offset.value }, 1000)
  document.addEventListener('visibilitychange', resume)
  window.addEventListener('online', resume)
})
onUnmounted(() => {
  stopped = true; controller?.abort(); clearTimeout(pollTimer); clearInterval(tickTimer)
  document.removeEventListener('visibilitychange', resume)
  window.removeEventListener('online', resume)
})
</script>

<template>
  <aside v-if="visible && !modalOpen" class="deployment-banner" role="status">
    <strong>{{ title }}</strong><span v-if="phase === 'scheduled'">{{ remaining ? `停机倒计时 ${countdownText(remaining)}` : '等待更新开始，请先保存内容' }}</span><span>{{ notice?.message }}</span>
    <button v-if="phase === 'scheduled'" @click="acknowledged = ''">查看公告</button>
    <button v-else @click="dismiss">知道了</button>
  </aside>
  <DialogRoot :open="modalOpen" @update:open="value => { if (!value) acknowledge() }">
    <DialogPortal><DialogOverlay class="deployment-overlay" /><DialogContent class="deployment-dialog" @escape-key-down="phase === 'maintenance' && $event.preventDefault()" @pointer-down-outside="$event.preventDefault()">
      <div class="deployment-symbol">{{ phase === 'maintenance' ? '…' : '!' }}</div>
      <DialogTitle class="deployment-title">{{ title }}</DialogTitle>
      <DialogDescription class="deployment-message">{{ notice?.message }}</DialogDescription>
      <div v-if="phase === 'scheduled'" class="deployment-countdown"><span>{{ remaining ? '距离暂时停止服务还有' : '倒计时已结束，等待更新开始' }}</span><b>{{ countdownText(remaining) }}</b><p>请先保存当前内容。倒计时期间仍可继续操作。</p></div>
      <p v-if="phase === 'maintenance'" class="deployment-help">页面内容会保留。请等待恢复提示，避免反复提交或刷新。</p>
      <p v-if="!connected" class="deployment-help">正在等待服务器恢复连接…</p>
      <div class="deployment-actions"><button v-if="phase === 'scheduled'" @click="acknowledge">知道了，先保存</button><template v-else-if="phase !== 'maintenance'"><button @click="acknowledge">保留当前页面</button><button v-if="phase === 'completed'" class="deployment-primary" @click="refresh">我已保存，刷新页面</button></template></div>
    </DialogContent></DialogPortal>
  </DialogRoot>
</template>

<style>
.deployment-overlay{position:fixed;inset:0;background:#102a43aa;backdrop-filter:blur(3px);z-index:1000}.deployment-dialog{position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);z-index:1001;width:min(480px,calc(100vw - 32px));max-height:90vh;overflow:auto;border:1px solid #b8ddd3;border-radius:20px;background:#fff;padding:32px;box-shadow:0 20px 80px #0f172a55;color:#334155;text-align:center}.deployment-symbol{margin:0 auto 16px;width:48px;height:48px;display:grid;place-items:center;border-radius:50%;background:#fff4d7;color:#995e12;font-size:28px;font-weight:700}.deployment-title{font-size:22px;font-weight:700;color:#163f36;margin-bottom:12px}.deployment-message,.deployment-help{font-size:14px;line-height:1.8}.deployment-help{margin-top:16px;color:#64748b}.deployment-countdown{margin:20px 0;background:#f1f8f5;padding:20px;border-radius:12px}.deployment-countdown span{font-size:13px;color:#64748b}.deployment-countdown b{display:block;font-size:48px;font-variant-numeric:tabular-nums;color:#146452;letter-spacing:3px}.deployment-countdown p{font-size:13px;line-height:1.6}.deployment-actions{display:flex;justify-content:center;gap:10px;margin-top:24px;flex-wrap:wrap}.deployment-actions button,.deployment-banner button{padding:9px 14px;background:#edf5f1;color:#146452;border:1px solid #c6dfd5;border-radius:8px;cursor:pointer}.deployment-actions .deployment-primary{background:#146452;color:white}.deployment-banner{position:fixed;top:12px;left:50%;transform:translateX(-50%);z-index:999;width:max-content;max-width:calc(100vw - 24px);display:flex;align-items:center;justify-content:center;flex-wrap:wrap;gap:10px;border:1px solid #e4c276;border-radius:12px;padding:12px 18px;background:#fffbeb;color:#785020;box-shadow:0 6px 24px #0f172a22;font-size:13px}.deployment-banner strong{font-size:14px}
</style>

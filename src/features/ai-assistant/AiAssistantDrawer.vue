<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Bot, RefreshCcw, ShieldCheck, Sparkles, X } from '@lucide/vue'
import { useRoute } from 'vue-router'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import AiBusinessResultCard from './AiBusinessResultCard.vue'
import AiAttachmentTray from './AiAttachmentTray.vue'
import AiComposer from './AiComposer.vue'
import AiMessageList from './AiMessageList.vue'
import AiSuggestedPrompts from './AiSuggestedPrompts.vue'
import AiToolActivity from './AiToolActivity.vue'
import { buildAIPageContext, isAIBusinessRoute, supportsAIVisionContext } from './pageContext'
import { suggestedPrompts } from './promptPresets'
import { useAIAssistantStore } from './store'

interface ComposerHandle {
  clear: () => void
  focus: () => void
}

interface AttachmentTrayHandle {
  addFiles: (files: FileList | readonly File[]) => Promise<void>
  clear: () => void
  prepareForSend: () => Promise<{
    attachments: import('./types').AIRequestAttachment[]
    consent: import('./types').AICloudProcessingConsent | null
  } | null>
  resetConsent: () => void
}

const route = useRoute()
const appStore = useAppStore()
const authStore = useAuthStore()
const assistantStore = useAIAssistantStore()
const trigger = ref<HTMLButtonElement | null>(null)
const drawer = ref<HTMLElement | null>(null)
const composer = ref<ComposerHandle | null>(null)
const attachmentTray = ref<AttachmentTrayHandle | null>(null)
let releaseDrawerScrollLock: BodyScrollLockRelease | null = null

const isEligibleRoute = computed(() => isAIBusinessRoute(route))
const isEligibleSession = computed(() => Boolean(
  authStore.isAuthenticated
  && !authStore.currentUser?.force_password_change,
))
const isEligible = computed(() => isEligibleSession.value && isEligibleRoute.value)
const isVisible = computed(() => isEligible.value && assistantStore.canUse)
const pageContext = computed(() => buildAIPageContext(
  route,
  String(appStore.activeFactoryId),
))
const canAttachImages = computed(() => Boolean(
  assistantStore.capabilities?.vision_enabled === true
  && supportsAIVisionContext(pageContext.value),
))
const prompts = computed(() => suggestedPrompts(pageContext.value))

function focusableElements() {
  if (!drawer.value) return []
  return [...drawer.value.querySelectorAll<HTMLElement>(
    'button:not([disabled]), a[href], textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => !element.hasAttribute('hidden') && element.getAttribute('aria-hidden') !== 'true')
}

async function openDrawer() {
  if (!isEligible.value) return
  await assistantStore.loadCapabilities(true)
  if (!isVisible.value) return
  assistantStore.openDrawer()
  void nextTick(() => composer.value?.focus())
}

function closeDrawer(restoreFocus = true) {
  if (!assistantStore.isOpen) return
  attachmentTray.value?.clear()
  assistantStore.closeDrawer()
  if (restoreFocus && isVisible.value) {
    void nextTick(() => trigger.value?.focus())
  }
}

function handleDrawerKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    closeDrawer()
    return
  }
  if (event.key !== 'Tab') return
  const elements = focusableElements()
  if (!elements.length) {
    event.preventDefault()
    drawer.value?.focus()
    return
  }
  const first = elements[0]
  const last = elements.at(-1)
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last?.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first?.focus()
  }
}

async function sendMessage(prompt: string) {
  let batch: {
    attachments: import('./types').AIRequestAttachment[]
    consent: import('./types').AICloudProcessingConsent | null
  } = { attachments: [], consent: null }
  if (canAttachImages.value) {
    const prepared = await attachmentTray.value?.prepareForSend()
    if (prepared === null) return
    batch = prepared ?? batch
  }
  // Build after any asynchronous image reads so route/factory context cannot go stale.
  const context = buildAIPageContext(route, String(appStore.activeFactoryId))
  composer.value?.clear()
  try {
    await assistantStore.sendMessage(prompt, context, batch.attachments, batch.consent)
  } finally {
    if (batch.attachments.length) attachmentTray.value?.clear()
  }
}

async function retryLastTextRequest() {
  const context = buildAIPageContext(route, String(appStore.activeFactoryId))
  await assistantStore.retryLastTextRequest(context)
}

function droppedFiles(event: DragEvent | ClipboardEvent) {
  return event.type === 'drop'
    ? (event as DragEvent).dataTransfer?.files
    : (event as ClipboardEvent).clipboardData?.files
}

function handleFileTransfer(event: DragEvent | ClipboardEvent) {
  const files = droppedFiles(event)
  if (!files?.length) return
  event.preventDefault()
  if (!canAttachImages.value || assistantStore.isStreaming) return
  void attachmentTray.value?.addFiles(files)
}

function handleDragOver(event: DragEvent) {
  if (event.dataTransfer?.types.includes('Files')) event.preventDefault()
}

watch(
  () => authStore.sessionVersion,
  async () => {
    attachmentTray.value?.clear()
    assistantStore.resetForSession()
    if (isEligible.value) await assistantStore.loadCapabilities(true)
  },
  { immediate: true },
)

watch(isEligible, async (eligible) => {
  if (!eligible) {
    attachmentTray.value?.clear()
    assistantStore.closeDrawer()
    return
  }
  await assistantStore.loadCapabilities()
})

watch(isVisible, (visible) => {
  if (!visible && assistantStore.isOpen) assistantStore.closeDrawer()
})

watch(pageContext, (context) => {
  if (!context?.factory_id) attachmentTray.value?.clear()
})

watch(() => route.fullPath, () => attachmentTray.value?.resetConsent())
watch(() => appStore.activeFactoryId, () => attachmentTray.value?.resetConsent())

watch(
  () => assistantStore.isOpen,
  (open) => {
    if (open) {
      releaseDrawerScrollLock ??= acquireBodyScrollLock()
      return
    }
    releaseDrawerScrollLock?.()
    releaseDrawerScrollLock = null
  },
)

onBeforeUnmount(() => {
  attachmentTray.value?.clear()
  assistantStore.resetForSession()
  releaseDrawerScrollLock?.()
  releaseDrawerScrollLock = null
})
</script>

<template>
  <Teleport to="body">
    <button
      v-if="isVisible && !assistantStore.isOpen"
      id="ai-assistant-trigger"
      ref="trigger"
      type="button"
      class="ai-assistant-trigger fixed bottom-5 right-4 z-[85] inline-flex h-12 items-center gap-2 rounded-2xl bg-slate-950 px-4 text-sm font-semibold text-white shadow-[0_18px_48px_rgba(15,23,42,0.28)] transition hover:-translate-y-0.5 hover:bg-sky-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600 sm:bottom-6 sm:right-6"
      aria-haspopup="dialog"
      aria-controls="ai-assistant-drawer"
      :aria-expanded="assistantStore.isOpen"
      @click="openDrawer"
    >
      <Sparkles class="size-4" aria-hidden="true" />
      AI 助手
    </button>

    <Transition name="ai-drawer">
      <div
        v-if="isVisible && assistantStore.isOpen"
        class="fixed inset-0 z-[90] bg-slate-950/35 backdrop-blur-[1px]"
        role="presentation"
        @mousedown.self="closeDrawer()"
      >
        <aside
          id="ai-assistant-drawer"
          ref="drawer"
          class="absolute inset-0 flex min-h-0 flex-col bg-slate-50 shadow-2xl outline-none sm:inset-y-0 sm:left-auto sm:w-[min(430px,100vw)] sm:border-l sm:border-slate-200"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ai-assistant-title"
          aria-describedby="ai-assistant-description"
          tabindex="-1"
          @paste="handleFileTransfer"
          @dragover="handleDragOver"
          @drop="handleFileTransfer"
          @keydown="handleDrawerKeydown"
        >
          <header class="flex shrink-0 items-center gap-3 border-b border-slate-200 bg-white px-4 py-3.5 sm:px-5">
            <span class="flex size-10 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white" aria-hidden="true">
              <Bot class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <h2 id="ai-assistant-title" class="text-sm font-bold text-slate-950">Nexus AI 助手</h2>
              <p id="ai-assistant-description" class="mt-0.5 flex items-center gap-1 text-[11px] text-slate-500">
                <ShieldCheck class="size-3 text-emerald-600" aria-hidden="true" />
                仅访问当前账号已授权的信息
              </p>
            </div>
            <button
              type="button"
              class="flex size-9 items-center justify-center rounded-xl text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
              aria-label="关闭 AI 助手并清空对话"
              @click="closeDrawer()"
            >
              <X class="size-4" aria-hidden="true" />
            </button>
          </header>

          <section
            data-ai-pilot-status
            class="shrink-0 border-b border-sky-100 bg-sky-50 px-4 py-2.5 text-[11px] leading-4 text-sky-900 sm:px-5"
            aria-label="AI Pilot 服务状态"
          >
            <p class="font-semibold">Pilot 已准入 · 只读模式</p>
            <p class="mt-0.5 text-sky-700">
              服务端已授权文字流式回答{{ assistantStore.capabilities?.vision_enabled ? '与受控页面图片' : '' }}；AI 不会直接写入业务数据。
            </p>
          </section>

          <AiMessageList :messages="assistantStore.messages">
            <AiToolActivity :items="assistantStore.activities" />
            <AiBusinessResultCard
              :results="assistantStore.businessResults"
              :sources="assistantStore.sources"
            />
            <div
              v-if="assistantStore.lastError || assistantStore.canRetry"
              class="mx-4 mt-2 rounded-xl border px-3 py-2 text-xs leading-5 sm:mx-5"
              :class="assistantStore.lastError
                ? 'border-rose-200 bg-rose-50 text-rose-700'
                : 'border-amber-200 bg-amber-50 text-amber-800'"
            >
              <p v-if="assistantStore.lastError" role="alert">{{ assistantStore.lastError }}</p>
              <p v-else>本次生成已停止，业务页面未受影响。</p>
              <button
                v-if="assistantStore.canRetry"
                type="button"
                class="mt-1.5 inline-flex items-center gap-1 font-semibold text-sky-700 hover:text-sky-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
                aria-label="仅重新发送上一条文字问题"
                @click="retryLastTextRequest"
              >
                <RefreshCcw class="size-3.5" aria-hidden="true" />
                仅重试文字
              </button>
            </div>
            <AiSuggestedPrompts
              v-if="!assistantStore.messages.length"
              :prompts="prompts"
              :disabled="assistantStore.isStreaming"
              @select="sendMessage"
            />
          </AiMessageList>
          <AiAttachmentTray
            v-if="canAttachImages"
            ref="attachmentTray"
            :disabled="assistantStore.isStreaming"
          />
          <AiComposer
            ref="composer"
            :streaming="assistantStore.isStreaming"
            :attachments-enabled="canAttachImages"
            @cancel="assistantStore.cancelActiveRequest"
            @send="sendMessage"
          />
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ai-drawer-enter-active,
.ai-drawer-leave-active {
  transition: opacity 180ms ease;
}

.ai-drawer-enter-active aside,
.ai-drawer-leave-active aside {
  transition: transform 220ms ease;
}

.ai-drawer-enter-from,
.ai-drawer-leave-to {
  opacity: 0;
}

.ai-drawer-enter-from aside,
.ai-drawer-leave-to aside {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .ai-drawer-enter-active,
  .ai-drawer-leave-active,
  .ai-drawer-enter-active aside,
  .ai-drawer-leave-active aside {
    transition: none;
  }

  .ai-assistant-trigger {
    transition: none;
  }
}
</style>

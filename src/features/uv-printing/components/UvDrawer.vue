<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { acquireBodyScrollLock, type BodyScrollLockRelease } from '@/lib/bodyScrollLock'

/**
 * 右侧检查器抽屉 / 窄屏覆盖层。
 *
 * - 桌面：主视图 + 侧检查器；平板与手机：同一实例作为覆盖层；
 * - role="dialog" + aria-modal，打开后聚焦容器，Tab 焦点保持在层内，
 *   Escape 关闭，关闭后焦点回到原来的触发元素；
 * - 正在提交或业务禁止关闭时给出反馈。
 */

const props = withDefaults(defineProps<{
  open: boolean
  title: string
  subtitle?: string
  /** 宽度档位：详情 560 / 检查器 480 / 现场录入 420。 */
  size?: 'sm' | 'md' | 'lg' | 'full'
  /** 关闭会丢草稿时置 true，Escape 会先要求确认。 */
  busy?: boolean
  closeHint?: string
}>(), {
  subtitle: '',
  size: 'md',
  busy: false,
  closeHint: '按 Esc 关闭',
})

const emit = defineEmits<{ close: [] }>()
const panel = ref<HTMLElement | null>(null)
let releaseScrollLock: BodyScrollLockRelease | null = null
let lastActive: HTMLElement | null = null

const sizeClass = computed(() => ({
  sm: 'uv-drawer--sm',
  md: 'uv-drawer--md',
  lg: 'uv-drawer--lg',
  full: 'uv-drawer--full',
}[props.size]))

function focusables(): HTMLElement[] {
  if (!panel.value) return []
  return [...panel.value.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
  )].filter((element) => element.offsetParent !== null || element === document.activeElement)
}

function onKeydown(event: KeyboardEvent) {
  if (!props.open) return
  if (event.key === 'Escape') {
    event.stopPropagation()
    emit('close')
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables()
  if (!items.length) return
  const first = items[0]!
  const last = items[items.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, async (open) => {
  if (open) {
    lastActive = document.activeElement as HTMLElement | null
    releaseScrollLock = acquireBodyScrollLock()
    document.addEventListener('keydown', onKeydown, true)
    await nextTick()
    panel.value?.focus()
  } else {
    document.removeEventListener('keydown', onKeydown, true)
    releaseScrollLock?.()
    releaseScrollLock = null
    lastActive?.focus?.()
    lastActive = null
  }
})
</script>

<template>
  <Transition name="uv-drawer">
    <div
      v-if="open"
      class="uv-drawer-layer"
      role="presentation"
      @click.self="emit('close')"
    >
      <section
        ref="panel"
        class="uv-drawer"
        :class="sizeClass"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        tabindex="-1"
      >
        <header class="uv-drawer__head">
          <div class="uv-drawer__titles">
            <h2 class="uv-drawer__title">{{ title }}</h2>
            <p v-if="subtitle" class="uv-drawer__subtitle">{{ subtitle }}</p>
          </div>
          <div class="uv-drawer__head-actions">
            <span class="uv-drawer__hint">{{ closeHint }}</span>
            <Button
              variant="ghost"
              size="icon-sm"
              type="button"
              :aria-label="`关闭${title}`"
              @click="emit('close')"
            >
              <X class="size-4" aria-hidden="true" />
            </Button>
          </div>
        </header>

        <div class="uv-drawer__body">
          <slot />
        </div>

        <footer v-if="$slots.actions" class="uv-drawer__foot">
          <p v-if="busy" class="uv-drawer__busy" role="status">正在提交，完成后才允许关闭。</p>
          <div class="uv-drawer__foot-actions">
            <slot name="actions" />
          </div>
        </footer>
      </section>
    </div>
  </Transition>
</template>

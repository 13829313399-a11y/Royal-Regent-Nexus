<script setup lang="ts">
import { computed } from 'vue'
import { AlertTriangle, Ban, ChevronRight, Loader2, RefreshCw, SearchX } from '@lucide/vue'
import { Button } from '@/components/ui/button'

/**
 * 统一的异步区块状态：加载 / 空 / 无结果 / 无权限 / 只读 / 失败 / 过期。
 * 任何页面都不得用「0」或空白代替失败。
 */

export type UvSurfaceState =
  | 'idle'
  | 'loading'
  | 'ready'
  | 'empty'
  | 'no-result'
  | 'forbidden'
  | 'readonly'
  | 'error'
  | 'stale'

const props = withDefaults(defineProps<{
  state: UvSurfaceState
  /** 该区块在业务上叫什么，用于把文案说清楚。 */
  subject?: string
  /** 失败时的可读原因。 */
  message?: string
  /** 失败时的错误码或请求范围，便于排查。 */
  detail?: string
  retryable?: boolean
  /** 空状态下的下一步指引。 */
  hint?: string
  compact?: boolean
}>(), {
  subject: '数据',
  message: '',
  detail: '',
  retryable: false,
  hint: '',
  compact: false,
})

const emit = defineEmits<{ retry: []; action: [] }>()

const isLoading = computed(() => props.state === 'loading')
const isFailure = computed(() => props.state === 'error' || props.state === 'stale')
const showContent = computed(() => props.state === 'ready' || props.state === 'readonly')
</script>

<template>
  <div
    v-if="isLoading"
    class="uv-state"
    :class="compact ? 'uv-state--compact' : ''"
    role="status"
    aria-live="polite"
  >
    <div class="uv-state__icon uv-state__icon--busy" aria-hidden="true">
      <Loader2 class="size-5 motion-safe:animate-spin" />
    </div>
    <p class="uv-state__title">正在读取{{ subject }}</p>
    <p class="uv-state__hint">读取完成前不会显示任何上一条口径的数字。</p>
    <div class="uv-skeleton-lines" aria-hidden="true">
      <span class="uv-skeleton-shimmer" />
      <span class="uv-skeleton-shimmer" />
      <span class="uv-skeleton-shimmer uv-skeleton-shimmer--short" />
    </div>
  </div>

  <div
    v-else-if="isFailure"
    class="uv-state uv-state--error"
    :class="compact ? 'uv-state--compact' : ''"
    role="alert"
  >
    <div class="uv-state__icon uv-state__icon--error" aria-hidden="true">
      <AlertTriangle class="size-5" />
    </div>
    <p class="uv-state__title">{{ state === 'stale' ? `${subject}已过期` : `读取${subject}失败` }}</p>
    <p class="uv-state__message">{{ message || '接口没有返回可用数据，这里不是「0」，也不回落样例数据。' }}</p>
    <p v-if="detail" class="uv-state__detail">{{ detail }}</p>
    <div v-if="retryable" class="uv-state__actions">
      <Button variant="outline" size="sm" type="button" @click="emit('retry')">
        <RefreshCw class="size-3.5" aria-hidden="true" />
        重试读取
      </Button>
    </div>
  </div>

  <div
    v-else-if="state === 'forbidden'"
    class="uv-state uv-state--warning"
    :class="compact ? 'uv-state--compact' : ''"
    role="alert"
  >
    <div class="uv-state__icon uv-state__icon--warning" aria-hidden="true">
      <Ban class="size-5" />
    </div>
    <p class="uv-state__title">没有查看{{ subject }}的权限</p>
    <p class="uv-state__message">{{ message || '当前账号在华康A生产部没有对应 UV 权限码，敏感字段也不会下发到前端。' }}</p>
    <p v-if="detail" class="uv-state__detail">{{ detail }}</p>
  </div>

  <div
    v-else-if="state === 'empty' || state === 'no-result'"
    class="uv-state"
    :class="compact ? 'uv-state--compact' : ''"
  >
    <div class="uv-state__icon" aria-hidden="true">
      <SearchX class="size-5" />
    </div>
    <p class="uv-state__title">
      {{ state === 'no-result' ? `没有符合条件的${subject}` : `当前范围还没有${subject}` }}
    </p>
    <p class="uv-state__hint">
      {{ hint || (state === 'no-result'
        ? '可以放宽业务日期或清除筛选后再看。'
        : '这是真实空数据，不是读取失败；产生记录后会自动出现在这里。') }}
    </p>
    <div v-if="state === 'no-result'" class="uv-state__actions">
      <Button variant="ghost" size="sm" type="button" @click="emit('action')">
        清除筛选
        <ChevronRight class="size-3.5" aria-hidden="true" />
      </Button>
    </div>
  </div>

  <slot v-else-if="showContent" />

  <slot v-else name="idle">
    <div class="uv-state uv-state--compact">
      <p class="uv-state__hint">尚未开始读取{{ subject }}。</p>
    </div>
  </slot>
</template>

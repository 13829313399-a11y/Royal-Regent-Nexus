<script setup lang="ts" generic="T">
import { computed, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight } from '@lucide/vue'

const props = withDefaults(defineProps<{
  items: T[]
  pageSize?: number
  total?: number
  offset?: number
}>(), {
  pageSize: 5,
  total: 0,
  offset: 0,
})

const page = ref(0)
const pageCount = computed(() => Math.max(1, Math.ceil(props.items.length / props.pageSize)))
const visibleItems = computed(() => props.items.slice(
  page.value * props.pageSize,
  (page.value + 1) * props.pageSize,
))
const firstVisible = computed(() => props.items.length ? props.offset + page.value * props.pageSize + 1 : 0)
const lastVisible = computed(() => props.offset + Math.min((page.value + 1) * props.pageSize, props.items.length))
const serverHasMore = computed(() => props.total > props.offset + props.items.length)

watch(() => props.items, () => { page.value = 0 })
</script>

<template>
  <div data-paged-result-list>
    <ul v-if="items.length" class="space-y-2">
      <li v-for="(item, index) in visibleItems" :key="page * pageSize + index">
        <slot :item="item" />
      </li>
    </ul>
    <slot v-else name="empty" />
    <nav v-if="pageCount > 1" class="mt-2 flex items-center justify-between rounded-lg border border-slate-200 bg-white px-2 py-1.5" aria-label="当前结果分页">
      <button
        type="button"
        class="inline-flex size-7 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        aria-label="上一页"
        :disabled="page === 0"
        @click="page -= 1"
      >
        <ChevronLeft class="size-3.5" aria-hidden="true" />
      </button>
      <span class="text-[10px] font-medium text-slate-500">第 {{ firstVisible }}–{{ lastVisible }} 条</span>
      <button
        type="button"
        class="inline-flex size-7 items-center justify-center rounded-md text-slate-600 hover:bg-slate-100 disabled:opacity-40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-600"
        aria-label="下一页"
        :disabled="page >= pageCount - 1"
        @click="page += 1"
      >
        <ChevronRight class="size-3.5" aria-hidden="true" />
      </button>
    </nav>
    <p v-if="serverHasMore" class="mt-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-2 text-[10px] leading-4 text-amber-800">
      仍有更多正式数据未在本次结果中返回。请继续查看下一页。
    </p>
  </div>
</template>

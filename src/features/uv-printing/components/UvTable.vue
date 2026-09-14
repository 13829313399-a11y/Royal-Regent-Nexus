<script setup lang="ts">
/**
 * 数据表外壳：语义化表格 + 独立横向滚动容器。
 *
 * - 只有表容器滚动，页面不整体溢出；
 * - 表头保持语义与键盘可达（排序按钮是真按钮）；
 * - 空/错/权限由外层 UvStateBlock 承担，本组件只负责结构。
 */

export interface UvColumn {
  key: string
  label: string
  /** 内容最小宽度，px；用于保持数字列不被压缩。 */
  width?: number
  align?: 'left' | 'right' | 'center'
  /** 说明列口径，渲染为表头副标题。 */
  hint?: string
  sortable?: boolean
  /** 该列只在有相应权限时显示。 */
  permission?: string
}

withDefaults(defineProps<{
  columns: UvColumn[]
  /** 内容最小宽度，px。 */
  minWidth?: number
  dense?: boolean
  caption?: string
  /** 键盘说明，屏幕阅读器可见。 */
  keyboardHint?: string
  /** 当前排序键与方向。 */
  sortKey?: string
  sortDirection?: 'asc' | 'desc'
}>(), {
  minWidth: 960,
  dense: false,
  caption: '',
  keyboardHint: '使用 Tab 在表头与行之间移动，Enter 打开选中行的详情。',
  sortKey: '',
  sortDirection: 'asc',
})

const emit = defineEmits<{ sort: [key: string] }>()
</script>

<template>
  <div class="uv-table-wrap">
    <p v-if="keyboardHint" class="uv-table-hint">{{ keyboardHint }}</p>
    <div class="uv-table-scroll" role="region" tabindex="0" :aria-label="caption || '数据表'">
      <table class="uv-table" :class="dense ? 'uv-table--dense' : ''" :style="{ minWidth: `${minWidth}px` }">
        <caption v-if="caption" class="uv-table-caption">{{ caption }}</caption>
        <thead>
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              scope="col"
              :style="column.width ? { width: `${column.width}px` } : undefined"
              :class="[`uv-table-cell--${column.align ?? 'left'}`]"
            >
              <button
                v-if="column.sortable"
                type="button"
                class="uv-table-sort"
                :aria-pressed="sortKey === column.key"
                @click="emit('sort', column.key)"
              >
                <span>{{ column.label }}</span>
                <span class="uv-table-sort__mark" aria-hidden="true">
                  {{ sortKey === column.key ? (sortDirection === 'asc' ? '↑' : '↓') : '↕' }}
                </span>
                <span class="sr-only">
                  {{ sortKey === column.key
                    ? `按${column.label}排序，当前${sortDirection === 'asc' ? '升序' : '降序'}`
                    : `按${column.label}排序` }}
                </span>
              </button>
              <template v-else>{{ column.label }}</template>
              <span v-if="column.hint" class="uv-table-th-hint">{{ column.hint }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <slot />
        </tbody>
        <tfoot v-if="$slots.foot">
          <slot name="foot" />
        </tfoot>
      </table>
    </div>
  </div>
</template>

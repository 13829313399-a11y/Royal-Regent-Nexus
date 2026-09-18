<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { departments, getDepartmentRoute, isModuleDepartmentId, type ModuleDepartmentId } from '@/data/enterpriseMock'
import { Button } from '@/components/ui/button'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()

const departmentTabs = departments.filter((department) => department.id !== 'overview')
const activeDepartmentId = computed<ModuleDepartmentId>(() => {
  const routeDepartment = String(route.params.department ?? '')
  return isModuleDepartmentId(routeDepartment) ? routeDepartment : appStore.activeDepartmentId
})

function selectDepartment(departmentId: ModuleDepartmentId) {
  appStore.setActiveDepartment(departmentId)
  router.push({
    path: getDepartmentRoute(departmentId),
    query: {
      ...route.query,
      factory: appStore.activeFactoryId,
    },
  })
}

/**
 * 滑动指示器：只做视觉增强。
 * 状态来源始终是路由，指示层不接收点击、不参与状态判断。
 * 首次定位直接落位（`data-ready="false"` 时隐藏），避免从左端穿过所有选项。
 */
const trackRef = ref<HTMLElement | null>(null)
const indicatorRef = ref<HTMLElement | null>(null)
const indicatorReady = ref(false)
const indicatorStyle = ref<Record<string, string>>({})
let resizeObserver: ResizeObserver | null = null

function measureIndicator() {
  const track = trackRef.value
  if (!track) return

  const activeButton = track.querySelector<HTMLElement>(`[data-department-id="${activeDepartmentId.value}"]`)
  if (!activeButton) {
    indicatorReady.value = false
    return
  }

  // 位置相对滚动容器内容计算，窄屏横向滚动时不会追错目标。
  const left = activeButton.offsetLeft
  const width = activeButton.offsetWidth
  const height = activeButton.offsetHeight
  indicatorStyle.value = {
    transform: `translate3d(${left}px, 0, 0)`,
    width: `${width}px`,
    height: `${height}px`,
  }
  indicatorReady.value = true
}

async function refreshIndicator() {
  await nextTick()
  measureIndicator()
}

onMounted(() => {
  void refreshIndicator()
  // 字体就绪后会改变按钮宽度，需要重新量测一次。
  if (typeof document !== 'undefined' && document.fonts?.ready) {
    void document.fonts.ready.then(() => measureIndicator())
  }
  if (typeof ResizeObserver !== 'undefined' && trackRef.value) {
    resizeObserver = new ResizeObserver(() => measureIndicator())
    resizeObserver.observe(trackRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  resizeObserver = null
})

watch(activeDepartmentId, () => {
  void refreshIndicator()
})
</script>

<template>
  <div ref="trackRef" class="portal-tabs" role="navigation" aria-label="部门切换">
    <span
      ref="indicatorRef"
      class="portal-tabs__indicator"
      :data-ready="indicatorReady ? 'true' : 'false'"
      :style="indicatorStyle"
      aria-hidden="true"
    />
    <Button
      v-for="department in departmentTabs"
      :key="department.id"
      type="button"
      size="lg"
      :variant="department.id === activeDepartmentId ? 'default' : 'ghost'"
      :class="['portal-tab', { 'portal-tab--current': department.id === activeDepartmentId }]"
      class="min-w-24"
      :data-department-id="department.id"
      :data-portal-current="department.id === activeDepartmentId ? 'true' : 'false'"
      :aria-current="department.id === activeDepartmentId ? 'page' : undefined"
      @click="selectDepartment(department.id as ModuleDepartmentId)"
    >
      {{ department.name }}
    </Button>
  </div>
</template>

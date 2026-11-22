<script setup lang="ts">
import { computed } from 'vue'
import { CircleAlert, CircleCheck, Info, RefreshCw } from '@lucide/vue'
import { Button, Popover, PopoverContent, PopoverTrigger } from '@/components/ui'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { sourceLabel, workHealth } from './health'
import type { WorkSnapshot } from './types'
const props = defineProps<{ snapshot?: WorkSnapshot | null; syncing?: boolean; badge?: boolean }>()
defineEmits<{ retry: []; navigate: [] }>()
const health = computed(() => workHealth(props.snapshot))
</script>
<template>
  <Popover v-if="badge"
    ><PopoverTrigger as-child
      ><Button
        variant="ghost"
        size="sm"
        :aria-label="'核验状态与覆盖范围：' + (health?.title || (snapshot ? '已核验' : '待同步'))"
        ><component
          :is="syncing ? RefreshCw : health?.warning ? CircleAlert : health ? Info : CircleCheck"
          :size="15"
          :class="syncing ? 'nc-spin' : health?.warning ? 'text-amber-700' : 'text-primary'"
        />{{
          syncing
            ? '同步中'
            : !snapshot
              ? '待同步'
              : health?.warning
                ? '需核对'
                : health
                  ? '来源说明'
                  : '已核验'
        }}</Button
      ></PopoverTrigger
    >
    <PopoverContent class="nc-health-card" align="end" aria-label="核验与覆盖说明"
      ><h3>核验与覆盖范围</h3>
      <p v-if="snapshot">上次同步 {{ formatBusinessDateTime(snapshot.health.as_of) }}（上海时间）</p>
      <p>责任与可办理范围由当前源业务核验。</p>
      <p v-if="snapshot?.health.coverage.length">
        已接入：{{
          snapshot.health.coverage
            .filter((x) => x.state === 'active')
            .map((x) => sourceLabel(x.module))
            .join('、')
        }}
      </p>
      <template v-if="health"
        ><strong>{{ health.title }}</strong>
        <p>{{ health.description }}</p>
        <ul v-if="health.details.length">
          <li v-for="detail in health.details" :key="detail">{{ detail }}</li>
        </ul></template
      ></PopoverContent
    >
  </Popover>
  <div v-else-if="health?.warning" class="nc-alert" role="alert">
    <CircleAlert :size="16" /><span
      >{{ health.title
      }}<small v-if="snapshot?.health.status === 'stale'"
        >上次同步 {{ formatBusinessDateTime(snapshot.health.as_of) }}</small
      ></span
    ><Button v-if="health.retryable" size="sm" variant="ghost" :disabled="syncing" @click="$emit('retry')"
      >重试同步</Button
    ><Button v-else-if="health.verificationCount" size="sm" variant="ghost" as-child
      ><RouterLink
        :to="{ name: 'notification-center', query: { view: 'verification' } }"
        @click="$emit('navigate')"
        >查看待核对</RouterLink
      ></Button
    >
  </div>
</template>

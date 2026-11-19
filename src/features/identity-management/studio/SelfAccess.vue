<script setup lang="ts">
import { computed } from 'vue'
import { Check, Clock3, Layers3, ListChecks, MapPin, ShieldCheck } from '@lucide/vue'
import { positionStatus, type PositionReview, type SelfPositionProfile } from '@/api/positionReviews'
import { formatBusinessDateTime } from '@/lib/dateTime'
import { departmentName, permissionName } from '../positionLabels'

const props = defineProps<{ data: SelfPositionProfile; latest?: PositionReview | null }>()
const steps = computed(() => {
  const review = props.latest
  if (!review) return []
  return [
    { title: review.origin === 'admin' ? '管理员发起' : '提交申请', description: formatBusinessDateTime(review.created_at), state: 'done' },
    { title: '管理员核验', description: review.status === 'pending' ? '等待核验' : '', state: review.status === 'pending' ? 'current' : ['applied', 'returned'].includes(review.status) ? 'done' : '' },
    { title: '退回补充', description: review.status === 'returned' ? '请查看处理意见' : '按需办理', state: review.status === 'returned' ? 'current' : '' },
    { title: '正式生效', description: review.status === 'applied' ? formatBusinessDateTime(review.updated_at) : '', state: review.status === 'applied' ? 'done' : '' },
  ]
})
const factoryName = (id: string) => props.data.reference_factories?.find(f => f.id === id)?.name || id
const accessKind = (kind: string) => kind === 'read' ? '查看' : kind === 'operate' ? '操作' : kind
</script>
<template>
  <section class="self-section">
    <header class="self-section-heading"><h2><ListChecks :size="18" />最近申请进度</h2><strong v-if="latest" class="self-outcome" :data-status="latest.status">{{ positionStatus[latest.status] }}</strong></header>
    <template v-if="latest">
      <p class="self-progress-position">{{ latest.declaration.position }}</p>
      <ol class="self-steps">
        <li v-for="(step, index) in steps" :key="step.title" :data-state="step.state" :aria-current="step.state === 'current' ? 'step' : undefined">
          <span class="self-step-dot" aria-hidden="true"><Check v-if="step.state === 'done'" :size="12" /><template v-else>{{ index + 1 }}</template></span>
          <strong>{{ step.title }}</strong><small v-if="step.description">{{ step.description }}</small>
        </li>
      </ol>
      <p v-if="latest.review_comment && !data.open_review" class="self-progress-note">{{ latest.review_comment }}</p>
    </template>
    <p v-else class="self-empty"><Clock3 :size="17" />暂无岗位申请。</p>
  </section>
  <section class="self-section">
    <header class="self-section-heading"><h2><ShieldCheck :size="18" />分模块有效权限</h2><small v-if="data.effective_permissions_grouped">{{ data.effective_permissions_grouped.length }} 个模块</small></header>
    <div v-if="data.effective_permissions_grouped?.length" class="self-modules">
      <article v-for="group in data.effective_permissions_grouped" :key="group.module_code" class="self-module">
        <h3>{{ group.module_name }}<span>{{ group.items.length }} 项</span></h3>
        <ul><li v-for="item in group.items.slice(0, 3)" :key="item.code"><span>{{ permissionName(item.code, item.name) }}</span><small>{{ accessKind(item.access_kind) }}</small></li></ul>
        <details><summary>查看全部权限与适用范围</summary>
          <div v-for="item in group.items" :key="item.code" class="self-scope"><b>{{ permissionName(item.code, item.name) }}</b> <small>{{ accessKind(item.access_kind) }}</small>
            <p v-if="item.factory_names.length"><MapPin :size="12" />{{ item.factory_names.join('、') }}</p>
            <p v-for="scope in item.scopes" :key="scope.factory_id">{{ item.factory_names[item.factory_ids.indexOf(scope.factory_id)] || scope.factory_id }} · {{ scope.department_codes.map(departmentName).join('、') }}</p>
          </div>
        </details>
      </article>
    </div>
    <p v-else class="self-empty">{{ data.effective_permissions_grouped ? '暂无生效能力。' : '分模块权限暂不可用。' }}</p>
  </section>
  <details v-if="data.current_packages?.length" class="self-section self-bindings">
    <summary><Layers3 :size="17" />当前权限包绑定明细 <small>{{ data.current_packages.length }} 条</small></summary>
    <ul><li v-for="p in data.current_packages" :key="p.binding_id"><strong>{{ p.role_name }}</strong><span>{{ departmentName(p.department) }}</span><span v-if="p.factory_id">{{ factoryName(p.factory_id) }}</span><small v-if="p.valid_until">有效至 {{ formatBusinessDateTime(p.valid_until) }}</small></li></ul>
  </details>
</template>

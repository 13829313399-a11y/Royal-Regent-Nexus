<script setup lang="ts">
import { Check, ArrowRight } from '@lucide/vue'
import type { RegisterResponse } from '@/api/auth'
import { formatBusinessDateTime } from '@/lib/dateTime'
defineProps<{ receipt: RegisterResponse; summary: { username: string; name: string; organization: string; department: string; position: string } }>()
defineEmits<{ login: []; restart: [] }>()
</script>
<template>
  <section class="ng-receipt ng-page-enter">
    <div class="ng-success-icon"><Check class="ng-icon" aria-hidden="true" /></div>
    <h1 tabindex="-1" data-auth-receipt-title>申请已收到</h1>
    <p class="ng-receipt-copy">账号正在等待管理员核验，审批通过后即可登录。</p>
    <div class="ng-receipt-status" role="status">等待管理员审批</div>
    <ol class="ng-progress-story"><li><div><strong>申请已提交</strong><span>你的账号与岗位资料已收到。</span></div></li><li><div><strong>管理员核验</strong><span>核对组织、部门和真实职位。</span></div></li><li><div><strong>审批通过后登录</strong><span>账号启用后，使用申请时设置的密码登录。</span></div></li></ol>
    <div class="ng-summary"><dl><dt>申请人</dt><dd>{{ summary.name }} · {{ summary.username }}</dd><dt>组织</dt><dd>{{ summary.organization }} / {{ summary.department }}</dd><dt>职位</dt><dd>{{ summary.position }}</dd><template v-if="receipt.request_id"><dt>申请编号</dt><dd>{{ receipt.request_id }}</dd></template><template v-if="receipt.submitted_at"><dt>提交时间</dt><dd>{{ formatBusinessDateTime(receipt.submitted_at) }}</dd></template></dl></div>
    <button class="ng-primary" type="button" @click="$emit('login')">返回登录<ArrowRight class="ng-icon ng-arrow" aria-hidden="true" /></button>
    <button type="button" class="ng-text-link auth-restart" @click="$emit('restart')">再申请一个账号</button>
  </section>
</template>

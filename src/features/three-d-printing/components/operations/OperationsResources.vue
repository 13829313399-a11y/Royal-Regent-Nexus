<script setup lang="ts">
import { useOperationsContext } from "../../operationsContext";
import PageControls from "../PageControls.vue";
import ProductPicker from "../ProductPicker.vue";
const {
  departments,
  canOperate,
  kind,
  items,
  page,
  total,
  loading,
  message,
  reason,
  resourceKey,
  revision,
  form,
  selectedFiles,
  labels,
  fields,
  states,
  fileItems,
  filePage,
  fileTotal,
  pending,
  selectedRun,
  feedback,
  editing,
  reset,
  load,
  edit,
  save,
  act,
  upload,
  loadFiles,
  download,
} = useOperationsContext();
</script>
<template>
  <div class="panel-card p-5">
    <h2 class="text-xl font-bold">生产协同</h2>
    <p class="mt-2 text-sm text-slate-600">
      先完善机台适配和卷材实测余量，再查看排程建议。建议需要人工保存计划，不会直接启动打印。
    </p>
    <p role="status" class="mt-3 text-amber-800">{{ message }}</p>
    <nav class="my-4 flex flex-wrap gap-2">
      <button
        v-for="(label, key) in labels"
        :key="key"
        class="action-button secondary"
        :class="{ 'ring-2 ring-teal-600': kind === key }"
        @click="kind = key"
      >
        {{ label }}
      </button>
    </nav>
    <p v-if="kind === 'spool'" class="mb-3 text-sm text-slate-600">
      卷材是物理余量台账；这里登记和盘点不会重复增加或扣减仓库总库存。低余量会提醒补料。
    </p>
    <form
      v-if="canOperate && kind !== 'file'"
      class="space-y-4"
      @submit.prevent="save"
    >
      <h3 class="font-bold">{{ editing ? "编辑记录" : "新增记录" }}</h3>
      <label v-if="kind === 'spool'"
        >卷材编号<input
          v-model="resourceKey"
          :disabled="editing"
          required
          maxlength="128"
      /></label>
      <div class="form-grid">
        <label v-for="field in fields[kind]" :key="field.name"
          >{{ field.label
          }}<ProductPicker
            v-if="field.type === 'product'"
            :model-value="String(form[field.name] ?? '')"
            @update:model-value="form[field.name] = $event" /><select
            v-else-if="field.name === 'department'"
            v-model="form[field.name]"
          >
            <option value="">选择申请部门</option>
            <option v-for="[key, label] in departments" :key="key" :value="key">
              {{ label }}
            </option></select
          ><select
            v-else-if="field.name === 'quality'"
            v-model="form[field.name]"
          >
            <option value="pending">待确认</option>
            <option value="passed">通过</option>
            <option value="failed">不通过</option></select
          ><select
            v-else-if="field.name === 'priority'"
            v-model="form[field.name]"
          >
            <option value="normal">普通</option>
            <option value="high">高</option>
            <option value="low">低</option></select
          ><input
            v-else-if="field.type === 'checkbox'"
            v-model="form[field.name]"
            type="checkbox" /><input
            v-else
            v-model="form[field.name]"
            :type="field.type === 'array' ? 'text' : (field.type ?? 'text')"
            :step="field.type === 'number' ? 'any' : undefined"
            maxlength="2000"
        /></label>
      </div>
      <div v-if="kind === 'request'">
        <p>关联附件</p>
        <label
          v-for="file in fileItems"
          :key="file.id"
          class="mr-4 inline-flex gap-2"
          ><input v-model="selectedFiles" type="checkbox" :value="file.id" />{{
            file.data.name
          }}</label
        ><PageControls
          :page="filePage"
          :total="fileTotal"
          @change="loadFiles"
        />
      </div>
      <label
        >保存 / 操作原因<input
          v-model="reason"
          required
          maxlength="500" /></label
      ><button class="action-button" :disabled="loading">保存</button
      ><button
        type="button"
        class="action-button secondary ml-2"
        @click="reset"
      >
        清空
      </button>
    </form>
    <label v-if="kind === 'file' && canOperate"
      >上传附件（最多10MB）<input
        type="file"
        accept=".3mf,.stl,.gcode,.pdf,.png,.jpg"
        :disabled="loading"
        @change="upload"
    /></label>
    <PageControls :page="page" :total="total" :busy="loading" @change="load" />
    <div class="divide-y">
      <article v-for="item in items" :key="item.id" class="py-4">
        <div class="flex flex-wrap justify-between gap-2">
          <strong>{{
            item.data.name ??
            item.data.lot ??
            item.data.file_name ??
            item.data.cost_center ??
            `机台 ${item.data.machine_no}`
          }}</strong
          ><span
            >{{ states[item.status] ?? item.status }} · 版本
            {{ item.revision }}</span
          >
        </div>
        <small class="break-all">{{ item.id }} · {{ item.resource_key }}</small>
        <p v-if="item.kind === 'spool'">
          {{ item.data.material }} · {{ item.data.color }} · 剩余
          {{ item.data.remaining_g }}g / {{ item.data.initial_g }}g ·
          {{
            item.data.machine_no
              ? `${item.data.machine_no}号机 / 槽${item.data.slot}`
              : "未上机"
          }}
          <b
            v-if="Number(item.data.remaining_g) <= Number(item.data.low_g)"
            class="text-rose-700"
            >低余量</b
          >
        </p>
        <p v-if="item.kind === 'request'">
          {{ item.data.department }} · {{ item.data.quantity }}件 · 交期
          {{ item.data.due_date }} · {{ item.data.note }}<br />计划
          {{ item.data.schedule_id ?? "待审批" }} · 生产记录
          {{ item.data.record_id ?? "待生产" }}
        </p>
        <p v-if="item.kind === 'profile'">
          材料 {{ item.data.materials }} · 保养间隔
          {{ item.data.service_interval_hours }}h ·
          {{ item.data.maintenance_blocked ? "暂停排程" : "可参与建议" }}
        </p>
        <p v-if="item.kind === 'file_alias'">
          {{ item.data.product_id }} · 版本 {{ item.data.version }} · 附件
          {{ item.data.file_id || "未关联" }}
        </p>
        <p v-if="item.kind === 'run_evidence'">
          生产记录 {{ item.data.record_id }} · {{ item.data.quality }} ·
          {{ item.data.note }}
        </p>
        <button
          v-if="item.kind === 'file'"
          class="action-button secondary mt-2"
          @click="download(item)"
        >
          下载附件
        </button>
        <div v-if="canOperate" class="mt-2 flex gap-2">
          <button
            v-if="
              item.kind !== 'file' &&
              ['active', 'submitted'].includes(item.status)
            "
            class="action-button secondary"
            @click="edit(item)"
          >
            编辑</button
          ><template v-if="item.kind === 'request'"
            ><button
              v-for="action in item.status === 'submitted'
                ? ['approve', 'reject', 'cancel']
                : item.status === 'approved'
                  ? ['schedule', 'cancel']
                  : item.status === 'scheduled'
                    ? ['complete']
                    : []"
              :key="action"
              class="action-button secondary"
              :disabled="loading"
              @click="act(item, action)"
            >
              {{
                {
                  approve: "批准",
                  reject: "驳回",
                  cancel: "取消",
                  schedule: "生成生产计划",
                  complete: "绑定完成凭证",
                }[action as "approve"]
              }}
            </button></template
          >
        </div>
      </article>
    </div>
    <p v-if="!items.length" class="py-5 text-slate-500">暂无记录</p>
    <div v-if="kind === 'request'" class="mt-4 space-y-2">
      <label>完成生产记录ID<input v-model="selectedRun" /></label
      ><label>验收反馈<input v-model="feedback" maxlength="2000" /></label>
      <p class="text-sm">
        完成时校验成功状态、产品和数量，已分配的生产记录不能重复绑定。
      </p>
    </div>
  </div>
</template>

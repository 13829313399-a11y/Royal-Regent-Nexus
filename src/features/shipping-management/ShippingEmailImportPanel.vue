<script setup lang="ts">
import { ref } from 'vue'
import { ChevronDown, CloudUpload, RefreshCw, UserRound } from '@lucide/vue'

const emit = defineEmits<{ notify: [message: string] }>()

const selectedFiles = ref<string[]>([])
const fileInput = ref<HTMLInputElement | null>(null)
const recordsOpen = ref(false)
const mailServer = ref('')
const mailAddress = ref('')
const mailPassword = ref('')

const summary = ref({
  warehouse: '南沙仓',
  vehicleType: '',
  country: '美国',
  inboundAt: '11/15 09:00',
  cutoffAt: '',
  bookingNo: 'SHZ8265013',
})

const summaryFields = [
  { key: 'warehouse', label: '仓库' },
  { key: 'vehicleType', label: '车类型' },
  { key: 'country', label: '收货国家' },
  { key: 'inboundAt', label: '入仓时间' },
  { key: 'cutoffAt', label: '截数期' },
  { key: 'bookingNo', label: '订舱号' },
] as const

const packingList = [
  { code: '15754', name: '链条枪', quantity: 12, cartons: 4, cbm: '2.4', grossWeight: '18.5' },
  { code: '92107', name: '泡泡棒', quantity: 24, cartons: 6, cbm: '3.1', grossWeight: '22.0' },
  { code: '88123', name: '户外水壶', quantity: 8, cartons: 2, cbm: '1.2', grossWeight: '9.6' },
  { code: '77201', name: '折叠椅', quantity: 6, cartons: 2, cbm: '1.8', grossWeight: '14.2' },
]

const records = [
  { subject: 'SHZ8265013 出货通知', from: 'shipping@customer.com', time: '11/13 09:42', status: '已解析', tone: 'blue' },
  { subject: 'SO 822 出货明细更新', from: 'ops@forwarder.com', time: '11/13 09:15', status: '已解析', tone: 'blue' },
  { subject: 'Fwd: 柜号 C260304887 装柜照片', from: 'warehouse@example.com', time: '11/13 08:51', status: '待复核', tone: 'orange' },
  { subject: 'SO 823 附件缺失', from: 'ops@forwarder.com', time: '11/13 08:20', status: '解析失败', tone: 'red' },
]

const statusDot: Record<string, string> = {
  blue: 'bg-blue-500',
  orange: 'bg-amber-500',
  red: 'bg-rose-500',
}

function preview(title: string) {
  emit('notify', `界面预览：${title}尚未接入后端接口。`)
}

function onFileChange(event: Event) {
  const files = [...((event.target as HTMLInputElement).files ?? [])]
  selectedFiles.value = files.map((file) => file.name)
  if (files.length) emit('notify', `已选择 ${files.length} 封邮件（界面预览，未实际上传）。`)
}

function onDrop(event: DragEvent) {
  const files = [...(event.dataTransfer?.files ?? [])]
  selectedFiles.value = files.map((file) => file.name)
  if (files.length) emit('notify', `已选择 ${files.length} 封邮件（界面预览，未实际上传）。`)
}

function openFilePicker() {
  fileInput.value?.click()
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div class="min-w-0">
        <h2 class="text-[16px] font-bold tracking-[-0.02em] text-emerald-950">邮件导入</h2>
        <p class="mt-0.5 text-[11px] text-slate-500">上传 .eml 或连接邮箱，自动解析出货单邮件。</p>
      </div>
      <span class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 text-[11px] font-medium text-emerald-900">
        <UserRound class="size-3.5" aria-hidden="true" />查看员 admin
      </span>
    </div>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4" aria-label="上传邮件">
      <div
        class="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-emerald-300/70 bg-emerald-50/40 px-4 py-10 text-center transition hover:border-emerald-400 hover:bg-emerald-100/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
        role="button"
        tabindex="0"
        aria-label="拖拽或点击上传 .eml 文件"
        @click="openFilePicker"
        @keydown.enter.prevent="openFilePicker"
        @keydown.space.prevent="openFilePicker"
        @dragover.prevent
        @drop.prevent="onDrop"
      >
        <span class="flex size-12 items-center justify-center rounded-full bg-emerald-100 text-emerald-700">
          <CloudUpload class="size-7" aria-hidden="true" />
        </span>
        <p class="mt-3 text-[13px] font-semibold text-emerald-950">将 .eml 文件拖到此处，或点击上传（支持多封邮件）</p>
        <p class="mt-1 text-[11px] text-emerald-800/60">单次可选择多个 .eml 文件，解析在浏览器本地完成。</p>
        <input ref="fileInput" type="file" accept=".eml" multiple class="hidden" @change="onFileChange">
      </div>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-800 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          @click="preview('解析邮件')"
        >
          解析邮件（{{ selectedFiles.length }}封）
        </button>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-100 px-4 text-[12px] font-semibold text-emerald-900 shadow-sm transition hover:bg-emerald-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-500"
          @click="preview('AI自动解析')"
        >
          AI自动解析
        </button>
        <span v-if="selectedFiles.length" class="text-[11px] text-slate-500">已选择 {{ selectedFiles.length }} 封邮件</span>
      </div>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4" aria-label="从邮箱直接导入">
      <h3 class="text-[13px] font-bold text-emerald-950">从邮箱直接导入</h3>
      <div class="mt-3 max-w-2xl space-y-2.5">
        <label class="flex items-center gap-3">
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">邮件服务器</span>
          <input
            v-model="mailServer"
            type="text"
            placeholder="imap.example.com"
            class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15"
          >
        </label>
        <label class="flex items-center gap-3">
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">邮箱地址</span>
          <input
            v-model="mailAddress"
            type="email"
            placeholder="shipping@example.com"
            class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15"
          >
        </label>
        <label class="flex items-center gap-3">
          <span class="w-20 shrink-0 text-right text-[12px] text-slate-600">密码</span>
          <input
            v-model="mailPassword"
            type="password"
            placeholder="••••••••"
            class="h-9 min-w-0 flex-1 rounded-lg border border-emerald-100 bg-white px-3 text-[12px] text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-3 focus:ring-emerald-500/15"
          >
        </label>
      </div>
      <button
        type="button"
        class="mt-4 inline-flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-blue-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500"
        @click="preview('保存并连接')"
      >
        保存并连接
      </button>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50" aria-label="解析记录">
      <div class="flex items-center justify-between gap-2 px-4 py-2.5">
        <button type="button" class="flex min-w-0 items-center gap-1.5 text-[13px] font-bold text-emerald-950" :aria-expanded="recordsOpen" @click="recordsOpen = !recordsOpen">
          <ChevronDown class="size-4 transition" :class="recordsOpen ? 'rotate-180' : ''" aria-hidden="true" />
          解析记录（4780）
        </button>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-emerald-200 bg-white px-2.5 text-[11px] font-semibold text-emerald-800 transition hover:border-emerald-300 hover:bg-emerald-50"
            @click="preview('刷新解析记录')"
          >
            <RefreshCw class="size-3.5" aria-hidden="true" />刷新
          </button>
          <button v-if="recordsOpen" type="button" class="text-[11px] text-slate-400 hover:text-slate-600" @click="recordsOpen = false">收起</button>
        </div>
      </div>
      <div v-if="recordsOpen" class="border-t border-emerald-100 px-4 py-2">
        <table class="w-full text-left text-[11px]">
          <thead class="text-slate-400">
            <tr>
              <th scope="col" class="py-1.5 font-medium">邮件主题</th>
              <th scope="col" class="py-1.5 font-medium">发件人</th>
              <th scope="col" class="py-1.5 font-medium">解析时间</th>
              <th scope="col" class="py-1.5 text-right font-medium">状态</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50 text-slate-600">
            <tr v-for="record in records" :key="record.subject">
              <td class="max-w-[280px] truncate py-1.5 font-medium text-slate-800">{{ record.subject }}</td>
              <td class="py-1.5">{{ record.from }}</td>
              <td class="py-1.5 tabular-nums">{{ record.time }}</td>
              <td class="py-1.5 text-right">
                <span class="inline-flex items-center gap-1.5">
                  <span class="size-1.5 rounded-full" :class="statusDot[record.tone]" aria-hidden="true" />
                  {{ record.status }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="rounded-xl border border-emerald-100/80 bg-gradient-to-b from-white to-emerald-50/50 p-4" aria-label="出货单草稿">
      <div class="grid gap-3 rounded-lg bg-emerald-50/70 px-3 py-2.5 sm:grid-cols-2 lg:grid-cols-6">
        <label v-for="field in summaryFields" :key="field.key" class="block min-w-0">
          <span class="block text-[10px] font-medium text-emerald-800/70">{{ field.label }}</span>
          <input
            v-model="summary[field.key]"
            type="text"
            placeholder="-"
            :aria-label="field.label"
            class="mt-0.5 h-6 w-full rounded border border-transparent bg-transparent px-0 text-[12px] font-semibold text-emerald-950 outline-none transition placeholder:text-slate-400 hover:border-emerald-200 focus:border-emerald-400 focus:bg-white"
          >
        </label>
      </div>

      <div class="mt-3 overflow-x-auto">
        <table class="w-full min-w-[560px] text-left text-[11px]">
          <caption class="pb-1.5 text-left text-[12px] font-bold text-emerald-950">Packing List 明细</caption>
          <thead class="bg-emerald-50/80 text-emerald-800/70">
            <tr>
              <th scope="col" class="px-2 py-1.5 font-medium">货号</th>
              <th scope="col" class="px-2 py-1.5 font-medium">品名</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">数量</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">箱数</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">CBM</th>
              <th scope="col" class="px-2 py-1.5 text-right font-medium">毛重（KG）</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-emerald-50 text-slate-600">
            <tr v-for="item in packingList" :key="item.code">
              <td class="px-2 py-1.5 font-semibold tabular-nums text-emerald-950">{{ item.code }}</td>
              <td class="px-2 py-1.5">{{ item.name }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.quantity }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.cartons }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.cbm }}</td>
              <td class="px-2 py-1.5 text-right tabular-nums">{{ item.grossWeight }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="mt-3 flex justify-end">
        <button
          type="button"
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-emerald-700 px-4 text-[12px] font-semibold text-white shadow-sm transition hover:bg-emerald-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-600"
          @click="preview('确认创建出货单')"
        >
          确认创建出货单
        </button>
      </div>
    </section>
  </div>
</template>

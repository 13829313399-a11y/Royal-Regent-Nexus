import { createRandomUuid } from "@/lib/randomUuid";
import {
  Activity,
  Archive,
  Boxes,
  CalendarDays,
  CirclePause,
  CirclePlay,
  Download,
  History,
  ImagePlus,
  PackagePlus,
  Printer,
  RefreshCw,
  Save,
  Settings2,
  ShieldCheck,
  Trash2,
  Wrench,
} from "@lucide/vue";
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from "vue";
import { useRouter } from "vue-router";
import { getApiErrorMessage } from "@/lib/http";
import { threeDPrintingApi } from "@/api/threeDPrinting";
import { useThreeDLive } from "@/composables/useThreeDLive";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import type {
  ThreeDAuditEvent,
  ThreeDDashboard,
  ThreeDMaintenance,
  ThreeDMaterial,
  ThreeDPrinter,
  ThreeDProduct,
  ThreeDProductionRecord,
  ThreeDSchedule,
} from "@/types/threeDPrinting";
export function useWorkspace() {
  type TabId =
    | "overview"
    | "machines"
    | "warehouse"
    | "reports"
    | "records"
    | "products"
    | "materials"
    | "schedules"
    | "maintenance"
    | "audit"
    | "migration"
    | "operations";

  const FACTORY_ID = "huakang-a" as const;
  const allTabs: { id: TabId; label: string; icon: typeof Printer }[] = [
    { id: "overview", label: "仪表盘", icon: Activity },
    { id: "machines", label: "机器状态", icon: Printer },
    { id: "warehouse", label: "材料仓库", icon: Archive },
    { id: "reports", label: "报表导出", icon: Download },
    { id: "records", label: "每日记录", icon: Activity },
    { id: "products", label: "产品库", icon: ImagePlus },
    { id: "materials", label: "材料管理", icon: Boxes },
    { id: "schedules", label: "排期表", icon: CalendarDays },
    { id: "maintenance", label: "维修记录", icon: Wrench },
    { id: "audit", label: "设置", icon: ShieldCheck },
    { id: "migration", label: "历史数据迁移", icon: History },
    { id: "operations", label: "生产协同", icon: Activity },
  ];

  const router = useRouter();
  const appStore = useAppStore();
  const authStore = useAuthStore();
  const tabs = computed(() =>
    allTabs.filter(
      (t) =>
        t.id !== "migration" ||
        (authStore.grants?.some(
          (g) =>
            g.role_id === "admin" && ["*", FACTORY_ID].includes(g.factory_id),
        ) &&
          canReadAudit.value),
    ),
  );
  const activeTab = ref<TabId>("overview");
  const dashboard = ref<ThreeDDashboard | null>(null);
  const auditEvents = ref<ThreeDAuditEvent[]>([]);
  const deletedRecords = ref<ThreeDProductionRecord[]>([]);
  const recordRequestKey = ref(createRandomUuid());
  const stockRequestKey = ref(createRandomUuid());
  const loading = ref(false);
  const saving = ref(false);
  const errorMessage = ref("");
  const successMessage = ref("");
  const productSearch = ref("");
  const dateFrom = ref("");
  const dateTo = ref("");
  let refreshTimer: ReturnType<typeof window.setInterval> | undefined;
  let liveRunVersion = "";
  let liveRefreshPending = false;
  let disposed = false;
  let liveSnapshotVersion = 0;
  let dashboardRequestVersion = 0;
  let dashboardInFlight = 0;
  let foregroundRequests = 0;
  const live = useThreeDLive((snapshot) => {
    if (disposed || !dashboard.value) return;
    liveSnapshotVersion++;
    dashboard.value.printers = snapshot.printers;
    dashboard.value.network_health = snapshot.network_health;
    if (snapshot.run_version !== liveRunVersion) liveRefreshPending = true;
    liveRunVersion = snapshot.run_version;
  });

  const canOperate = computed(() =>
    authStore.can("three_d_printing:operate", FACTORY_ID, "three-d-printing"),
  );
  const canUploadImage = computed(() =>
    authStore.can(
      "three_d_printing:image_upload",
      FACTORY_ID,
      "three-d-printing",
    ),
  );
  const canExport = computed(() =>
    authStore.can("three_d_printing:export", FACTORY_ID, "three-d-printing"),
  );
  const canControl = computed(() =>
    authStore.can(
      "three_d_printing:printer_control",
      FACTORY_ID,
      "three-d-printing",
    ),
  );
  const canReadAudit = computed(() =>
    authStore.can(
      "three_d_printing:audit_read",
      FACTORY_ID,
      "three-d-printing",
    ),
  );

  function todayText() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const day = String(now.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  const recordCostSnapshot = ref<Record<string, unknown> | undefined>();
  const pendingRecordImage = ref<File | null>(null);
  const recordImageUrl = ref("");
  const recordProductImageUrl = ref("");
  const recordImageRetry = ref<{ id: string; revision: number; file: File; key: string } | null>(null);
  const recordForm = reactive({
    reason: "",
    allow_negative_stock: false,
    history_only_correction: false,
    id: "",
    revision: 1,
    business_date: todayText(),
    machine_no: 1,
    status: "running" as "running" | "done" | "idle" | "fault",
    product_id: "",
    product_name: "",
    material_name: "",
    weight_g: 0,
    quantity: 1,
    duration_hours: 0,
    design_fee: 0,
    quoted_price: 0,
    customer: "",
    remark: "",
  });

  const productForm = reactive({
    id: "",
    revision: 1,
    name: "",
    customer: "",
    material_name: "",
    weight_g: 0,
    duration_hours: 0,
    default_quantity: 1,
    quoted_price: 0,
  });
  const pendingProductImage = ref<File | null>(null);
  const imageInputKey = ref(0);

  const materialForm = reactive({
    name: "",
    material_type: "",
    price_per_kg: 0,
  });

  const stockInForm = reactive({
    business_date: todayText(),
    material_name: "",
    amount_g: 1000,
    vendor: "",
    cost: 0,
    remark: "",
  });

  const scheduleForm = reactive({
    business_date: todayText(),
    product_id: "",
    product_name: "",
    customer: "",
    material_name: "",
    weight_g: 1,
    quantity: 1,
    machine_no: 0,
    priority: "normal" as "high" | "normal" | "low",
    status: "pending" as "pending" | "printing" | "done" | "cancelled",
    remark: "",
  });

  const maintenanceForm = reactive({
    business_date: todayText(),
    machine_no: 0,
    maintenance_type: "日常保养",
    description: "",
    cost: 0,
    vendor: "",
    remark: "",
  });

  const settingsForm = reactive({
    machine_count: 11,
    electricity_per_machine_day: 1.5,
    labor_per_day: 220,
    material_loss_rate: 1.2,
    profit_rate_percent: 40,
    revision: 1,
  });

  const listPages = reactive<
    Record<
      string,
      {
        page: number;
        total: number;
        q: string;
        quality: string;
        machine_no: number;
        state: string;
        source: string;
        customer: string;
        material: string;
        busy: boolean;
      }
    >
  >(
    Object.fromEntries(
      ["products", "records", "movements", "schedules", "maintenance"].map(
        (k) => [
          k,
          {
            page: 1,
            total: 0,
            q: "",
            quality: "",
            machine_no: 0,
            state: "",
            source: "",
            customer: "",
            material: "",
            busy: false,
          },
        ],
      ),
    ),
  );
  const selectedPrinter = ref("");
  const recordSearchAllDates = ref(false);
  function showProductRecords(name: string) {
    listPages.records!.q = name;
    listPages.records!.page = 1;
    recordSearchAllDates.value = true;
    activeTab.value = "records";
  }
  const queryVersions: Record<string, number> = {};
  async function loadPage(kind: string, page = 1) {
    const state = listPages[kind]!;
    const version = (queryVersions[kind] = (queryVersions[kind] ?? 0) + 1);
    state.busy = true;
    errorMessage.value = "";
    try {
      const result = await threeDPrintingApi.collection(kind, {
        page,
        page_size: 50,
        q: state.q,
        quality: state.quality,
        machine_no: state.machine_no,
        state: state.state,
        source: state.source,
        customer: state.customer,
        material: state.material,
        date_from: kind === "records" && recordSearchAllDates.value ? "" : dateFrom.value,
        date_to: kind === "records" && recordSearchAllDates.value ? "" : dateTo.value,
      });
      if (version !== queryVersions[kind] || !dashboard.value) return;
      if (page > 1 && result.items.length === 0) {
        await loadPage(kind, Math.max(1, Math.ceil(result.total / 50)));
        return;
      }
      state.page = page;
      state.total = result.total;
      Object.assign(dashboard.value, {
        [kind === "movements" ? "inventory_movements" : kind]: result.items,
      });
    } catch (error) {
      if (version === queryVersions[kind]) errorMessage.value = getApiErrorMessage(error);
    } finally {
      if (version === queryVersions[kind]) state.busy = false;
    }
  }
  const visibleProducts = computed(() => {
    const query = productSearch.value.trim().toLowerCase();
    if (!query) return dashboard.value?.products ?? [];
    return (dashboard.value?.products ?? []).filter((product) =>
      [product.name, product.customer, product.material_name].some((value) =>
        value.toLowerCase().includes(query),
      ),
    );
  });

  const printerMetrics = computed(() => {
    const printers = dashboard.value?.printers ?? [];
    return {
      total: printers.length,
      connected: printers.filter((printer) => printer.connected).length,
      running: printers.filter((printer) => printer.state === "RUNNING").length,
      paused: printers.filter((printer) => printer.state === "PAUSE").length,
    };
  });

  function stateLabel(state: string) {
    return (
      {
        RUNNING: "打印中",
        PAUSE: "已暂停",
        IDLE: "空闲",
        FINISH: "已完成",
        FAILED: "失败",
        ERROR: "异常",
        OFFLINE: "离线",
        STALE: "状态陈旧",
        UNKNOWN: "状态未知",
      }[state] ?? state
    );
  }

  function stateClass(printer: ThreeDPrinter) {
    if (!printer.connected) return "bg-slate-100 text-slate-600";
    if (printer.state === "RUNNING") return "bg-emerald-100 text-emerald-700";
    if (printer.state === "PAUSE") return "bg-amber-100 text-amber-700";
    if (["FAILED", "ERROR"].includes(printer.state))
      return "bg-rose-100 text-rose-700";
    return "bg-sky-100 text-sky-700";
  }

  function money(value: unknown) {
    return `¥${Number(value || 0).toFixed(2)}`;
  }

  function showSuccess(message: string) {
    successMessage.value = message;
    window.setTimeout(() => {
      if (successMessage.value === message) successMessage.value = "";
    }, 3500);
  }

  async function loadDashboard(background = false) {
    const requestVersion = ++dashboardRequestVersion;
    const snapshotVersion = liveSnapshotVersion;
    dashboardInFlight++;
    if (!background) { foregroundRequests++; loading.value = true; }
    try {
      const next = await threeDPrintingApi.dashboard(
        dateFrom.value,
        dateTo.value,
      );
      if (disposed || requestVersion !== dashboardRequestVersion) return;
      // The HTTP query may have begun before a newer live snapshot arrived.
      if (dashboard.value && snapshotVersion !== liveSnapshotVersion) {
        next.printers = dashboard.value.printers;
        next.network_health = dashboard.value.network_health;
      }
      dashboard.value = next;
      Object.assign(settingsForm, dashboard.value.settings);
      listPages.products!.total = Number(
        dashboard.value.summary.productCount || dashboard.value.products.length,
      );
      listPages.records!.total = Number(
        dashboard.value.summary.recordCount || dashboard.value.records.length,
      );
      if (
        ["products", "records", "schedules", "maintenance"].includes(
          activeTab.value,
        )
      )
        await loadPage(activeTab.value, listPages[activeTab.value]!.page);
      errorMessage.value = "";
    } catch (error) {
      if (!background) errorMessage.value = getApiErrorMessage(error);
    } finally {
      dashboardInFlight--;
      if (!background) { foregroundRequests--; loading.value = foregroundRequests > 0; }
    }
  }

  async function mutate(action: () => Promise<unknown>, success: string) {
    saving.value = true;
    errorMessage.value = "";
    try {
      await action();
      await loadDashboard(true);
      showSuccess(success);
      return true;
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error);
      return false;
    } finally {
      saving.value = false;
    }
  }

  function chooseRecordProduct(selected?: ThreeDProduct) {
    const product =
      selected ??
      dashboard.value?.products.find(
        (item) => item.id === recordForm.product_id,
      );
    if (!product) {
      recordProductImageUrl.value = "";
      return;
    }
    recordProductImageUrl.value = product.image_url || "";
    recordForm.product_name = product.name;
    recordForm.material_name = product.material_name;
    recordForm.weight_g = product.weight_g;
    recordForm.quantity = product.default_quantity;
    recordForm.duration_hours = product.duration_hours;
    recordForm.quoted_price = product.quoted_price;
    recordForm.customer = product.customer;
  }

  function resetRecordForm() {
    recordImageRetry.value = null;
    pendingRecordImage.value = null;
    recordImageUrl.value = "";
    recordProductImageUrl.value = "";
    recordCostSnapshot.value = undefined;
    recordRequestKey.value = createRandomUuid();
    Object.assign(recordForm, {
      reason: "",
      allow_negative_stock: false,
      history_only_correction: false,
      id: "",
      revision: 1,
      business_date: todayText(),
      machine_no: 1,
      status: "running",
      product_id: "",
      product_name: "",
      material_name: "",
      weight_g: 0,
      quantity: 1,
      duration_hours: 0,
      design_fee: 0,
      quoted_price: 0,
      customer: "",
      remark: "",
    });
  }

  function editRecord(record: ThreeDProductionRecord) {
    recordImageRetry.value = null;
    pendingRecordImage.value = null;
    recordImageUrl.value = record.record_image_url || "";
    recordProductImageUrl.value = record.product_image_url || "";
    recordCostSnapshot.value = record.calculated_cost_snapshot || {};
    Object.assign(recordForm, record, {
      reason: "",
      allow_negative_stock: false,
      history_only_correction: false,
    });
    recordRequestKey.value = createRandomUuid();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function submitRecord() {
    if (saving.value) return false;
    saving.value = true;
    errorMessage.value = "";
    const payload = {
      factory_id: FACTORY_ID,
      idempotency_key: recordRequestKey.value,
      reason: recordForm.reason,
      allow_negative_stock: recordForm.allow_negative_stock,
      history_only_correction: recordForm.history_only_correction,
      business_date: recordForm.business_date,
      machine_no: recordForm.machine_no,
      status: recordForm.status,
      product_id: recordForm.product_id,
      product_name: recordForm.product_name,
      material_name: recordForm.material_name,
      weight_g: recordForm.weight_g,
      quantity: recordForm.quantity,
      duration_hours: recordForm.duration_hours,
      design_fee: recordForm.design_fee,
      quoted_price: recordForm.quoted_price,
      customer: recordForm.customer,
      remark: recordForm.remark,
    };
    let recordSaved = false;
    try {
      // Resolve an uncertain image response with its original key before another record edit.
      if (recordImageRetry.value) {
        recordSaved = true;
        await uploadPendingRecordImage();
        recordSaved = false;
      }
      const record = await (recordForm.id
          ? threeDPrintingApi.updateRecord(recordForm.id, {
              ...payload,
              revision: recordForm.revision,
            })
          : threeDPrintingApi.createRecord(payload));
      recordSaved = true;
      // Persist the returned identity before uploading so retry cannot create another record.
      recordForm.id = record.id;
      recordForm.revision = record.revision;
      recordCostSnapshot.value = record.calculated_cost_snapshot;
      recordRequestKey.value = createRandomUuid();
      if (pendingRecordImage.value) {
        recordImageRetry.value = { id: record.id, revision: record.revision, file: pendingRecordImage.value, key: createRandomUuid() };
        await uploadPendingRecordImage();
      }
      await loadDashboard(true);
      showSuccess("记录已保存，请核对记录中的扣料状态");
      resetRecordForm();
      return true;
    } catch (error) {
      errorMessage.value = (recordSaved ? "记录已保存，" + (pendingRecordImage.value ? "图片上传失败，可重新保存重试：" : "列表刷新失败：") : "") + getApiErrorMessage(error);
      return false;
    } finally {
      saving.value = false;
    }
  }

  async function uploadPendingRecordImage() {
    const request = recordImageRetry.value!;
    const updated = await threeDPrintingApi.uploadRecordImage(request.id, request.revision, request.file, request.key);
    if (updated.revision !== request.revision + 1) {
      throw new Error("记录已被其他人修改，请关闭窗口并重新打开，避免覆盖他人的修改。");
    }
    recordForm.revision = updated.revision;
    recordImageUrl.value = updated.record_image_url || "";
    pendingRecordImage.value = null;
    recordImageRetry.value = null;
  }

  async function removeRecord(record: ThreeDProductionRecord) {
    if (
      !window.confirm(
        `确认撤销 ${record.business_date} · ${record.machine_no}号机记录？历史审计会保留。`,
      )
    )
      return;
    const reason = window
      .prompt("请输入撤销原因；系统将按原扣料流水返还库存")
      ?.trim();
    if (!reason) return;
    await mutate(
      () =>
        threeDPrintingApi.deleteRecord(
          record.id,
          record.revision,
          reason,
          `delete-${record.id}-${record.revision}`,
        ),
      "生产记录已撤销",
    );
  }

  function resetProductForm() {
    Object.assign(productForm, {
      id: "",
      revision: 1,
      name: "",
      customer: "",
      material_name: "",
      weight_g: 0,
      duration_hours: 0,
      default_quantity: 1,
      quoted_price: 0,
    });
    pendingProductImage.value = null;
    imageInputKey.value += 1;
  }

  function editProduct(product: ThreeDProduct) {
    Object.assign(productForm, product);
    pendingProductImage.value = null;
    imageInputKey.value += 1;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function selectProductImage(event: Event) {
    const input = event.target as HTMLInputElement;
    pendingProductImage.value = input.files?.[0] ?? null;
  }

  async function submitProduct() {
    saving.value = true;
    errorMessage.value = "";
    try {
      const payload = {
        factory_id: FACTORY_ID,
        name: productForm.name,
        customer: productForm.customer,
        material_name: productForm.material_name,
        weight_g: productForm.weight_g,
        duration_hours: productForm.duration_hours,
        default_quantity: productForm.default_quantity,
        quoted_price: productForm.quoted_price,
      };
      const product = productForm.id
        ? await threeDPrintingApi.updateProduct(productForm.id, {
            ...payload,
            revision: productForm.revision,
          })
        : await threeDPrintingApi.createProduct(payload);
      if (pendingProductImage.value) {
        await threeDPrintingApi.uploadProductImage(
          product.id,
          pendingProductImage.value,
        );
      }
      await loadDashboard(true);
      showSuccess(
        pendingProductImage.value ? "产品及图片已保存" : "产品已保存",
      );
      resetProductForm();
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error);
    } finally {
      saving.value = false;
    }
  }

  async function archiveProduct(product: ThreeDProduct) {
    if (
      !window.confirm(`确认停用产品“${product.name}”？历史生产记录不会删除。`)
    )
      return;
    await mutate(
      () => threeDPrintingApi.archiveProduct(product.id),
      "产品已停用",
    );
  }

  async function submitMaterial() {
    const ok = await mutate(
      () =>
        threeDPrintingApi.createMaterial({
          factory_id: FACTORY_ID,
          ...materialForm,
        }),
      "物料已新增",
    );
    if (ok)
      Object.assign(materialForm, {
        name: "",
        material_type: "",
        price_per_kg: 0,
      });
  }

  async function archiveMaterial(material: ThreeDMaterial) {
    if (!window.confirm(`确认停用物料“${material.name}”？历史流水不会删除。`))
      return;
    await mutate(
      () => threeDPrintingApi.archiveMaterial(material.id),
      "物料已停用",
    );
  }

  async function adjustStock(
    materialName: string,
    stock: number,
    minimum: number,
  ) {
    const inventory = dashboard.value?.inventory.find(
      (item) => item.material_name === materialName,
    );
    const raw = window.prompt(
      `将“${materialName}”库存调整为多少克？`,
      String(stock),
    );
    if (raw === null) return;
    const target = Number(raw);
    if (!Number.isFinite(target) || target < 0) {
      errorMessage.value = "库存必须是大于或等于 0 的数字";
      return;
    }
    const reason = window.prompt("请输入调整原因（必填）", "库存盘点调整");
    if (!reason?.trim()) return;
    await mutate(
      () =>
        threeDPrintingApi.adjustInventory(
          materialName,
          target,
          minimum,
          reason.trim(),
          inventory?.revision ?? 0,
          `adjust-${materialName}-${inventory?.revision ?? 0}`,
        ),
      "库存已调整并记录流水",
    );
  }

  async function submitStockIn() {
    const ok = await mutate(
      () =>
        threeDPrintingApi.stockIn({
          ...stockInForm,
          idempotency_key: stockRequestKey.value,
        }),
      "入库已登记",
    );
    if (ok) stockRequestKey.value = createRandomUuid();
    if (ok)
      Object.assign(stockInForm, {
        business_date: todayText(),
        material_name: "",
        amount_g: 1000,
        vendor: "",
        cost: 0,
        remark: "",
      });
  }

  function chooseScheduleProduct(selected?: ThreeDProduct) {
    const product =
      selected ??
      dashboard.value?.products.find(
        (item) => item.id === scheduleForm.product_id,
      );
    if (!product) return;
    scheduleForm.product_name = product.name;
    scheduleForm.customer = product.customer;
    scheduleForm.material_name = product.material_name;
    scheduleForm.weight_g = product.weight_g || 1;
    scheduleForm.quantity = product.default_quantity;
  }

  const scheduleEditId = ref("");
  const scheduleEditRevision = ref(1);
  function editSchedule(schedule: ThreeDSchedule) {
    for (const key of Object.keys(scheduleForm))
      Object.assign(scheduleForm, {
        [key]: schedule[key as keyof ThreeDSchedule],
      });
    scheduleEditId.value = schedule.id;
    scheduleEditRevision.value = schedule.revision;
  }
  async function submitSchedule() {
    const ok = await mutate(
      () =>
        scheduleEditId.value
          ? threeDPrintingApi.updateSchedule(scheduleEditId.value, {
              factory_id: FACTORY_ID,
              ...scheduleForm,
              revision: scheduleEditRevision.value,
            })
          : threeDPrintingApi.createSchedule({
              factory_id: FACTORY_ID,
              ...scheduleForm,
            }),
      "生产计划已保存",
    );
    if (ok) {
      scheduleEditId.value = "";
      Object.assign(scheduleForm, {
        business_date: todayText(),
        product_id: "",
        product_name: "",
        customer: "",
        material_name: "",
        weight_g: 1,
        quantity: 1,
        machine_no: 0,
        priority: "normal",
        status: "pending",
        remark: "",
      });
    }
  }

  async function changeScheduleStatus(
    schedule: ThreeDSchedule,
    status: ThreeDSchedule["status"],
  ) {
    await mutate(
      () =>
        threeDPrintingApi.updateScheduleStatus(
          schedule.id,
          status,
          schedule.revision,
        ),
      "计划状态已更新",
    );
  }

  async function removeSchedule(schedule: ThreeDSchedule) {
    if (!window.confirm(`确认删除计划“${schedule.product_name}”？`)) return;
    await mutate(
      () => threeDPrintingApi.deleteSchedule(schedule.id),
      "计划已删除",
    );
  }

  async function submitMaintenance() {
    const ok = await mutate(
      () =>
        threeDPrintingApi.createMaintenance({
          factory_id: FACTORY_ID,
          ...maintenanceForm,
        }),
      "维护记录已新增",
    );
    if (ok)
      Object.assign(maintenanceForm, {
        business_date: todayText(),
        machine_no: 0,
        maintenance_type: "日常保养",
        description: "",
        cost: 0,
        vendor: "",
        remark: "",
      });
  }

  async function removeMaintenance(record: ThreeDMaintenance) {
    if (!window.confirm(`确认删除 ${record.business_date} 的维护记录？`))
      return;
    await mutate(
      () => threeDPrintingApi.deleteMaintenance(record.id),
      "维护记录已删除",
    );
  }

  async function sendCommand(
    printer: ThreeDPrinter,
    action: "pause" | "resume",
  ) {
    const actionName = action === "pause" ? "暂停" : "恢复";
    if (!window.confirm(`确认远程${actionName} ${printer.machine_no}号机？`))
      return;
    const reason = window.prompt(`请输入${actionName}原因（将写入审计记录）`);
    if (!reason?.trim()) return;
    await mutate(
      () => threeDPrintingApi.command(printer, action, reason.trim()),
      `${actionName}指令已进入边缘代理队列`,
    );
  }

  async function saveSettings() {
    await mutate(
      () =>
        threeDPrintingApi.updateSettings({
          factory_id: FACTORY_ID,
          ...settingsForm,
        }),
      "计费设置已更新",
    );
  }

  async function restoreRecord(record: ThreeDProductionRecord) {
    const reason = window
      .prompt("恢复后将重新检查库存并扣料，请填写原因")
      ?.trim();
    if (!reason) return;
    if (
      await mutate(
        () =>
          threeDPrintingApi.restoreRecord(
            record.id,
            record.revision,
            reason,
            `restore-${record.id}-${record.revision}`,
          ),
        "记录已恢复，请核对扣料状态",
      )
    )
      await loadAudit();
  }

  async function toggleDayOff() {
    const day = dashboard.value?.day_statuses.find(
      (item) => item.business_date === recordForm.business_date,
    );
    const reason = window
      .prompt(
        day?.is_day_off
          ? "请输入恢复工作日的原因（撤销记录需在审计页逐条恢复）"
          : "将撤销当天全部记录并冲销扣料，请填写原因",
      )
      ?.trim();
    if (!reason) return;
    await mutate(
      () =>
        threeDPrintingApi.setDayOff(
          recordForm.business_date,
          !day?.is_day_off,
          day?.revision ?? 0,
          reason,
          `day-${recordForm.business_date}-${day?.revision ?? 0}`,
        ),
      "日期状态已更新",
    );
  }

  async function loadAudit() {
    if (!canReadAudit.value) return;
    try {
      [auditEvents.value, deletedRecords.value] = await Promise.all([
        threeDPrintingApi.audit(),
        threeDPrintingApi.deletedRecords(),
      ]);
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error);
    }
  }

  async function exportWorkbook() {
    saving.value = true;
    try {
      const blob = await threeDPrintingApi.exportWorkbook(
        dateFrom.value,
        dateTo.value,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `3D打印管理-${todayText()}.xlsx`;
      link.click();
      URL.revokeObjectURL(url);
      showSuccess("导出文件已生成");
    } catch (error) {
      errorMessage.value = getApiErrorMessage(error);
    } finally {
      saving.value = false;
    }
  }

  watch(activeTab, (tab) => {
    if (!["records", "overview", "reports"].includes(tab)) {
      dateFrom.value = "";
      dateTo.value = "";
    }
    if (tab === "audit") void loadAudit();
    if (["products", "records", "schedules", "maintenance"].includes(tab))
      void loadPage(tab);
    if (router.currentRoute?.value)
      void router.replace({
        query: { ...router.currentRoute.value.query, tab },
      });
  });

  onMounted(async () => {
    if (appStore.activeProductionFactory.id !== FACTORY_ID) {
      appStore.setActiveFactory(FACTORY_ID);
      await router.replace({
        query: { ...router.currentRoute.value.query, factory: FACTORY_ID },
      });
    }
    const tab = router.currentRoute?.value.query.tab;
    if (typeof tab === "string" && tabs.value.some((item) => item.id === tab))
      activeTab.value = tab as TabId;
    await loadDashboard();
    if (disposed) return;
    live.start();
    refreshTimer = window.setInterval(() => {
      if (!saving.value && !dashboardInFlight && (!live.connected.value || liveRefreshPending)) {
        liveRefreshPending = false;
        void loadDashboard(true);
      }
    }, 8000);
  });

  onBeforeUnmount(() => {
    disposed = true;
    live.stop();
    if (refreshTimer) window.clearInterval(refreshTimer);
  });

  return {
    recordSearchAllDates,
    showProductRecords,
    editSchedule,
    scheduleEditId,
    listPages,
    loadPage,
    selectedPrinter,
    FACTORY_ID,
    tabs,
    router,
    appStore,
    authStore,
    activeTab,
    dashboard,
    auditEvents,
    deletedRecords,
    recordRequestKey,
    stockRequestKey,
    loading,
    saving,
    errorMessage,
    successMessage,
    productSearch,
    dateFrom,
    dateTo,
    refreshTimer,
    liveRunVersion,
    liveRefreshPending,
    disposed,
    live,
    canOperate,
    canUploadImage,
    canExport,
    canControl,
    canReadAudit,
    recordForm,
    recordCostSnapshot,
    pendingRecordImage,
    recordImageUrl,
    recordProductImageUrl,
    recordImageRetry,
    productForm,
    pendingProductImage,
    imageInputKey,
    materialForm,
    stockInForm,
    scheduleForm,
    maintenanceForm,
    settingsForm,
    visibleProducts,
    printerMetrics,
    todayText,
    stateLabel,
    stateClass,
    money,
    showSuccess,
    loadDashboard,
    mutate,
    chooseRecordProduct,
    resetRecordForm,
    editRecord,
    submitRecord,
    removeRecord,
    resetProductForm,
    editProduct,
    selectProductImage,
    submitProduct,
    archiveProduct,
    submitMaterial,
    archiveMaterial,
    adjustStock,
    submitStockIn,
    chooseScheduleProduct,
    submitSchedule,
    changeScheduleStatus,
    removeSchedule,
    submitMaintenance,
    removeMaintenance,
    sendCommand,
    saveSettings,
    restoreRecord,
    toggleDayOff,
    loadAudit,
    exportWorkbook,
    Activity,
    Archive,
    Boxes,
    CalendarDays,
    CirclePause,
    CirclePlay,
    Download,
    History,
    ImagePlus,
    PackagePlus,
    Printer,
    RefreshCw,
    Save,
    Settings2,
    ShieldCheck,
    Trash2,
    Wrench,
  };
}

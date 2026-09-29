import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  collection: vi.fn(),
  updateSchedule: vi.fn(),
}));
vi.mock("@/lib/http", () => ({
  http: { get: mocks.get, post: mocks.post },
  getApiErrorMessage: (error: Error) => error.message,
}));
vi.mock("@/api/threeDPrinting", () => ({
  threeDPrintingApi: {
    collection: mocks.collection,
    updateSchedule: mocks.updateSchedule,
  },
}));
import OperationsPage from "../pages/OperationsPage.vue";
import ProductPicker from "../components/ProductPicker.vue";
import PageControls from "../components/PageControls.vue";
import EntityPicker from "../components/EntityPicker.vue";
import { workspaceKey } from "../context";

let wrapper: ReturnType<typeof mount>;
beforeEach(() => {
  vi.clearAllMocks();
  mocks.get.mockImplementation(async (url: string) => ({
    data: url.endsWith("/analytics")
      ? { machines: [] }
      : { items: [], total: 0, page: 1, page_size: 50 },
  }));
  mocks.collection.mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 50,
  });
});
afterEach(() => {
  wrapper?.unmount();
  vi.unstubAllGlobals();
});

describe("3D operations workspace", () => {
  it.each([false, true])("keeps analytics busy even if advice fails (%s)", async (adviceFails) => {
    let finish!: (value: unknown) => void;
    mocks.get.mockImplementation((url: string) => url.endsWith("/analytics")
      ? new Promise(resolve => { finish = resolve; })
      : adviceFails && url.endsWith("/recommendations") ? Promise.reject(new Error("建议暂不可用"))
      : Promise.resolve({ data: { items: [], total: 0, page: 1, page_size: 50 } }));
    wrapper = mount(OperationsPage, {
      global: { provide: { [workspaceKey as symbol]: {
        canOperate: ref(true), activeTab: ref("operations"), editSchedule: vi.fn(),
      } } },
    });
    await flushPromises();
    const button = () => wrapper.findAll("button").find(b => /正在计算|重新计算/.test(b.text()))!;
    expect(button().attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("正在汇总设备历史");
    await button().trigger("click");
    expect(mocks.get.mock.calls.filter(([url]) => url.endsWith("/analytics"))).toHaveLength(1);
    expect(mocks.get).toHaveBeenCalledWith("/three-d-printing/operations/analytics", { timeout: 90000 });
    finish({ data: { machines: [] } });
    await flushPromises();
    expect(button().attributes("disabled")).toBeUndefined();
    expect(wrapper.text()).not.toContain("正在汇总设备历史");
    if (adviceFails) {
      expect(wrapper.text()).toContain("建议暂不可用");
      mocks.get.mockResolvedValue({ data: { items: [], machines: [] } });
      await button().trigger("click");
      await flushPromises();
      expect(wrapper.text()).not.toContain("建议暂不可用");
    }
  });

  it("queries products beyond the dashboard first page and emits the selected model", async () => {
    const product = {
      id: "remote-product-1200",
      name: "远端产品",
      customer: "客户",
    };
    mocks.collection.mockResolvedValue({ items: [product], total: 1 });
    wrapper = mount(ProductPicker, { props: { modelValue: "" } });
    await wrapper.get("input").setValue("远端产品");
    await wrapper.get("button").trigger("click");
    await flushPromises();
    expect(mocks.collection).toHaveBeenCalledWith("products", {
      q: "远端产品",
      page_size: 50,
    });
    await wrapper.get("select").setValue(product.id);
    expect(wrapper.emitted("selected")?.[0]).toEqual([product]);
  });

  it("works without native randomUUID, preserves retry keys, and hides forms for readers", async () => {
    vi.stubGlobal("crypto", {
      getRandomValues: globalThis.crypto.getRandomValues.bind(globalThis.crypto),
    });
    const canOperate = ref(true);
    wrapper = mount(OperationsPage, {
      global: {
        provide: {
          [workspaceKey as symbol]: {
            canOperate,
            activeTab: ref("operations"),
            editSchedule: vi.fn(),
          },
        },
      },
    });
    await flushPromises();
    const form = wrapper.get("form");
    const input = (label: string) =>
      form
        .findAll("label")
        .find((item) => item.text() === label)!
        .get("input");
    await input("卷材编号").setValue("spool-qa");
    await input("材料").setValue("PLA");
    await input("批次").setValue("batch-qa");
    mocks.post
      .mockRejectedValueOnce(new Error("网络中断"))
      .mockResolvedValue({ data: {} });
    await form.trigger("submit");
    await flushPromises();
    const first = mocks.post.mock.calls[0]![1];
    expect(wrapper.text()).toContain("网络中断");
    await form.trigger("submit");
    await flushPromises();
    expect(mocks.post.mock.calls[1]![1].idempotency_key).toBe(
      first.idempotency_key,
    );
    expect(first.data.remaining_g).toBe(1000);
    expect(first.reason).toBe("保存卷材与 AMS");
    expect(first.idempotency_key).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    await input("卷材编号").setValue("spool-next");
    await form.trigger("submit");
    await flushPromises();
    expect(mocks.post.mock.calls[2]![1].idempotency_key).not.toBe(first.idempotency_key);
    canOperate.value = false;
    await flushPromises();
    expect(wrapper.find("form").exists()).toBe(false);
  });

  it("does not navigate beyond the last page or while loading", async () => {
    wrapper = mount(PageControls, {
      props: { page: 2, total: 51, busy: false },
    });
    const button = (name: string) => wrapper.findAll("button").find(b => b.text() === name)!;
    expect(button("下一页").attributes("disabled")).toBeDefined();
    expect(button("末页").attributes("disabled")).toBeDefined();
    await button("首页").trigger("click");
    expect(wrapper.emitted("change")?.[0]).toEqual([1]);
    await wrapper.setProps({ busy: true });
    expect(button("首页").attributes("disabled")).toBeDefined();
  });

  it("jumps directly to the last or typed page and bounds invalid page numbers", async () => {
    wrapper = mount(PageControls, { props: { page: 1, total: 1365 } });
    const button = (name: string) => wrapper.findAll("button").find(b => b.text() === name)!;
    await button("末页").trigger("click");
    expect(wrapper.emitted("change")?.at(-1)).toEqual([28]);
    await wrapper.setProps({ page: 28 });
    const input = wrapper.get('input[aria-label="跳转页码"]');
    await input.setValue(17);
    await input.trigger("keydown.enter");
    expect(wrapper.emitted("change")?.at(-1)).toEqual([17]);
    await wrapper.setProps({ page: 17 });
    await input.setValue(999);
    await button("跳转").trigger("click");
    expect(wrapper.emitted("change")?.at(-1)).toEqual([28]);
    await input.setValue(0);
    await button("跳转").trigger("click");
    expect(wrapper.emitted("change")?.at(-1)).toEqual([1]);
    const count = wrapper.emitted("change")!.length;
    await input.setValue("");
    await button("跳转").trigger("click");
    expect(wrapper.emitted("change")).toHaveLength(count);
    await wrapper.setProps({ busy: true });
    expect(button("跳转").attributes("disabled")).toBeDefined();
  });

  it("applies a named machine recommendation using the reviewed schedule revision", async () => {
    const schedule = {
      id: "job-1",
      factory_id: "huakang-a",
      revision: 4,
      product_id: "p1",
      product_name: "外壳",
      customer: "客户",
      material_name: "PLA",
      weight_g: 10,
      quantity: 2,
      machine_no: 0,
      priority: "normal",
      status: "pending",
      remark: "",
      business_date: "2026-09-30",
    };
    mocks.get.mockImplementation(async (url: string) => ({
      data: url.endsWith("recommendations")
        ? {
            items: [
              {
                schedule_id: "job-1",
                machine_no: 3,
                product_name: "外壳",
                quantity: 2,
                due_date: "2026-09-30",
                warnings: ["离线估算"],
                assigned: false,
                schedule,
              },
            ],
            notice: "离线估算",
          }
        : url.endsWith("analytics")
          ? { machines: [] }
          : { items: [], total: 0 },
    }));
    mocks.updateSchedule.mockResolvedValue({
      ...schedule,
      revision: 5,
      machine_no: 3,
    });
    wrapper = mount(OperationsPage, {
      global: {
        provide: {
          [workspaceKey as symbol]: {
            canOperate: ref(true),
            activeTab: ref("operations"),
            editSchedule: vi.fn(),
          },
        },
      },
    });
    await flushPromises();
    expect(wrapper.text()).toContain("外壳 · 2件");
    await wrapper
      .findAll("button")
      .find((b) => b.text() === "采用机台")!
      .trigger("click");
    await flushPromises();
    const { id, ...payload } = schedule;
    expect(mocks.updateSchedule).toHaveBeenCalledWith(id, {
      ...payload,
      machine_no: 3,
    });
    expect(mocks.post).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain("外壳已分配至3号机");
  });

  it("finds completion records by product and success state and uses readable labels", async () => {
    mocks.collection.mockResolvedValue({
      items: [
        {
          id: "record-1200",
          business_date: "2026-09-09",
          machine_no: 3,
          product_name: "外壳",
          quantity: 5,
        },
      ],
      total: 1,
    });
    wrapper = mount(EntityPicker, {
      props: {
        modelValue: "",
        kind: "records",
        state: "succeeded",
        productId: "part-123",
      },
    });
    await flushPromises();
    expect(mocks.collection).toHaveBeenCalledWith("records", {
      q: "",
      state: "succeeded",
      product_id: "part-123",
      page_size: 50,
    });
    expect(wrapper.text()).toContain("3号机 · 外壳 · 5件");
    await wrapper.get("select").setValue("record-1200");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual(["record-1200"]);
  });

  it("keeps selected spools when searching another batch and allows removal", async () => {
    mocks.get.mockResolvedValue({
      data: {
        items: [
          {
            id: "spool-2",
            resource_key: "S002",
            data: { material: "PLA", lot: "批次二", remaining_g: 700 },
          },
        ],
        total: 1,
      },
    });
    wrapper = mount(EntityPicker, {
      props: { modelValue: ["spool-1"], kind: "spool", multiple: true },
    });
    await flushPromises();
    await wrapper.get("input").setValue("批次二");
    await wrapper.findAll("button")[0]!.trigger("click");
    await flushPromises();
    expect(mocks.get).toHaveBeenLastCalledWith(
      "/three-d-printing/operations/resources/spool",
      { params: { q: "批次二", page_size: 50 } },
    );
    await wrapper.get("select").setValue("spool-2");
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([
      ["spool-1", "spool-2"],
    ]);
    await wrapper.setProps({ modelValue: ["spool-1", "spool-2"] });
    await wrapper
      .findAll("button")
      .find((b) => b.text().includes("S002"))!
      .trigger("click");
    expect(wrapper.emitted("update:modelValue")?.[1]).toEqual([["spool-1"]]);
  });
});

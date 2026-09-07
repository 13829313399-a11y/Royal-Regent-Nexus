import { flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";
const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  collection: vi.fn(),
}));
vi.mock("@/lib/http", () => ({
  http: { get: mocks.get, post: mocks.post },
  getApiErrorMessage: (error: Error) => error.message,
}));
vi.mock("@/api/threeDPrinting", () => ({
  threeDPrintingApi: { collection: mocks.collection },
}));
import OperationsPage from "../pages/OperationsPage.vue";
import ProductPicker from "../components/ProductPicker.vue";
import PageControls from "../components/PageControls.vue";
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
afterEach(() => wrapper?.unmount());

describe("3D operations workspace", () => {
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

  it("preserves a save retry key on failure and hides mutation forms for readers", async () => {
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
    await input("保存 / 操作原因").setValue("实测核对");
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
    canOperate.value = false;
    await flushPromises();
    expect(wrapper.find("form").exists()).toBe(false);
  });

  it("does not navigate beyond the last page or while loading", async () => {
    wrapper = mount(PageControls, {
      props: { page: 2, total: 51, busy: false },
    });
    expect(wrapper.findAll("button")[1]!.attributes("disabled")).toBeDefined();
    await wrapper.findAll("button")[0]!.trigger("click");
    expect(wrapper.emitted("change")?.[0]).toEqual([1]);
    await wrapper.setProps({ busy: true });
    expect(wrapper.findAll("button")[0]!.attributes("disabled")).toBeDefined();
  });
});

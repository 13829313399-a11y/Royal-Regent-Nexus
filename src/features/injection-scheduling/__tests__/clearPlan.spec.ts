// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { injectionApi } from '@/api/injectionScheduling';
import { useInjectionStore } from '@/stores/injectionScheduling';
import ClearPlanDialog from '../ClearPlanDialog.vue';

vi.mock('@/api/injectionScheduling', () => ({
  injectionApi: { get: vi.fn(), query: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));
const api = vi.mocked(injectionApi);
const wrappers: ReturnType<typeof mount>[] = [];
const preview = {
  factory_id: 'huaxing',
  revision: 40,
  preview_token: 'a'.repeat(64),
  confirmation_text: '清空华兴计划数据',
  can_clear: true,
  requires_execution_confirmation: true,
  counts: {
    demands: 280,
    manual_demands: 3,
    runs: 30,
    active_runs: 10,
    executed_runs: 11,
    shift_reports: 1,
    historical_outputs: 1449,
    import_batches: 1,
    machine_runtime_resets: 10,
  },
  preserved: { machines: 76, mold_masters: 5132, mold_assets: 197 },
  imports: [
    {
      id: 'batch-1',
      file_name: '导错.xlsx',
      sheet_name: '计划表',
      status: 'APPLIED',
    },
  ],
};
beforeEach(() => {
  setActivePinia(createPinia());
  vi.resetAllMocks();
  useInjectionStore().factory = 'huaxing';
  useInjectionStore().revision = 40;
  api.post.mockResolvedValue(preview);
});
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount());
  document.body.innerHTML = '';
});
async function open(props = { canPlan: true, canReport: true }) {
  const wrapper = mount(ClearPlanDialog, { props, attachTo: document.body });
  wrappers.push(wrapper);
  await flushPromises();
  return wrapper;
}
const button = (w: ReturnType<typeof mount>, label: string) =>
  w.findAll('button').find((b) => b.text() === label)!;

it('previews the entire factory independently of visible rows and cancels without writing', async () => {
  const store = useInjectionStore();
  store.filter = { field: 'mold_code', op: 'eq', value: 'ONE' };
  store.cursor = 200;
  const w = await open();
  expect(api.post).toHaveBeenCalledExactlyOnceWith('/plan-data/clear-preview', {
    factory_id: 'huaxing',
  });
  expect(w.text()).toContain('不受当前筛选或分页影响');
  expect(w.text()).toContain('3 条手工新增需求');
  expect(w.text()).toContain('5,132 条公共模具');
  expect(store.dirty).toBe(true);
  await button(w, '取消').trigger('click');
  expect(w.emitted('close')).toHaveLength(1);
  expect(api.post).toHaveBeenCalledTimes(1);
  w.unmount();
  expect(store.dirty).toBe(false);
});

it('clears the displayed scope including production records with one confirmation click', async () => {
  const store = useInjectionStore();
  const mutate = vi.spyOn(store, 'mutate').mockResolvedValue({ cleared: true });
  const w = await open();
  expect(w.find('input, textarea').exists()).toBe(false);
  expect(w.text()).toContain('点击“确认清除”将一并删除这些生产记录');
  expect(button(w, '重新预览')).toBeUndefined();
  expect(mutate).not.toHaveBeenCalled();
  expect(button(w, '确认清除').attributes('disabled')).toBeUndefined();
  await button(w, '确认清除').trigger('click');
  await flushPromises();
  expect(mutate).toHaveBeenCalledExactlyOnceWith('/plan-data/clear', {
    expected_revision: 40,
    preview_token: preview.preview_token,
    confirmation: preview.confirmation_text,
    reason: '用户确认清除本厂计划数据',
    include_execution: true,
  });
  expect(w.emitted('cleared')).toHaveLength(1);
});

it('does not offer an execution reset to an account without report permission', async () => {
  const w = await open({ canPlan: true, canReport: false });
  expect(w.text()).toContain('没有报工权限');
  expect(button(w, '确认清除').attributes('disabled')).toBeDefined();
});

it('does not require report permission or the extra checkbox for an unstarted import', async () => {
  const mutate = vi.spyOn(useInjectionStore(), 'mutate').mockResolvedValue({ cleared: true });
  api.post.mockResolvedValue({
    ...preview,
    requires_execution_confirmation: false,
  });
  const w = await open({ canPlan: true, canReport: false });
  expect(w.find('input[type="checkbox"]').exists()).toBe(false);
  expect(button(w, '确认清除').attributes('disabled')).toBeUndefined();
  await button(w, '确认清除').trigger('click');
  expect(mutate).toHaveBeenCalledExactlyOnceWith('/plan-data/clear', {
    expected_revision: 40,
    preview_token: preview.preview_token,
    confirmation: preview.confirmation_text,
    reason: '用户确认清除本厂计划数据',
    include_execution: false,
  });
});

it('requires a fresh preview and another confirmation click after a failed clear', async () => {
  const store = useInjectionStore();
  const mutate = vi.spyOn(store, 'mutate').mockImplementation(async () => {
    store.error = '预览后资料已更新，请重新预览清空范围';
    return null;
  });
  const w = await open();
  await button(w, '确认清除').trigger('click');
  await flushPromises();
  expect(w.get('[role="alert"]').text()).toContain('重新预览');
  expect(w.emitted('cleared')).toBeUndefined();
  expect(button(w, '确认清除').attributes('disabled')).toBeDefined();
  api.post.mockResolvedValue({
    ...preview,
    revision: 41,
    preview_token: 'b'.repeat(64),
  });
  await button(w, '重新预览').trigger('click');
  await flushPromises();
  expect(mutate).toHaveBeenCalledTimes(1);
  expect(button(w, '确认清除').attributes('disabled')).toBeUndefined();
  mutate.mockResolvedValue({ cleared: true });
  await button(w, '确认清除').trigger('click');
  await flushPromises();
  expect(mutate).toHaveBeenLastCalledWith('/plan-data/clear', expect.objectContaining({
    expected_revision: 41,
    preview_token: 'b'.repeat(64),
  }));
  expect(w.emitted('cleared')).toHaveLength(1);
});

it('keeps clearing unavailable for empty data or a failed preview', async () => {
  api.post.mockRejectedValue(new Error('预览失败'));
  const w = await open();
  expect(w.get('[role="alert"]').text()).toBeTruthy();
  expect(button(w, '确认清除').attributes('disabled')).toBeDefined();
  api.post.mockResolvedValue({
    ...preview,
    can_clear: false,
    requires_execution_confirmation: false,
  });
  await button(w, '重新预览').trigger('click');
  await flushPromises();
  expect(w.text()).toContain('暂无可清空');
  expect(w.find('textarea').exists()).toBe(false);
  expect(button(w, '确认清除').attributes('disabled')).toBeDefined();
});

it('discards a late preview after switching factory', async () => {
  let resolve!: (value: unknown) => void;
  api.post.mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const w = mount(ClearPlanDialog, {
    props: { canPlan: true, canReport: true },
  });
  wrappers.push(w);
  useInjectionStore().factory = 'huadeng';
  await flushPromises();
  resolve(preview);
  await flushPromises();
  expect(w.emitted('close')).toHaveLength(1);
  expect(w.find('textarea').exists()).toBe(false);
});

it('does not close or submit a second clear while the write is pending', async () => {
  const store = useInjectionStore();
  let resolve!: (value: unknown) => void;
  const mutate = vi.spyOn(store, 'mutate').mockImplementation(() => {
    store.busy = true;
    return new Promise((r) => {
      resolve = r;
    });
  });
  const w = await open();
  await button(w, '确认清除').trigger('click');
  await w.get('[role="dialog"]').trigger('keydown', { key: 'Escape' });
  expect(w.emitted('close')).toBeUndefined();
  expect(button(w, '取消').attributes('disabled')).toBeDefined();
  expect(mutate).toHaveBeenCalledTimes(1);
  store.busy = false;
  resolve({ cleared: true });
  await flushPromises();
});

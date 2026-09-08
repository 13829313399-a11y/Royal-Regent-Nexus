// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { injectionApi } from '@/api/injectionScheduling';
import { useInjectionStore } from '@/stores/injectionScheduling';
import MachineBoard from '../components/MachineBoard.vue';
import BulkStartDialog from '../BulkStartDialog.vue';
import type { StartReviewRow } from '../bulkStart';

vi.mock('@/api/injectionScheduling', () => ({
  injectionApi: { get: vi.fn(), query: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));
const api = vi.mocked(injectionApi);
const wrappers: ReturnType<typeof mount>[] = [];
const machines = Array.from({ length: 76 }, (_, i) => ({
  id: `m${i}`,
  code: `旧${i + 1}`,
  operating_status: 'IDLE',
  revision: 1,
}));
const queues = Object.fromEntries(
  machines.map((m) => [
    m.id,
    [
      {
        id: `r${m.id}`,
        machine_id: m.id,
        status: 'PLANNED',
        revision: 1,
        snapshot: { mold_code: `模具${m.id}` },
      },
    ],
  ]),
);
const reviewed = (id: string, can_start = true): StartReviewRow => ({
  machine_id: id,
  run_id: `r${id}`,
  machine_code: id,
  mold_code: `模具${id}`,
  order_no: 'ORDER-1',
  remaining_shots: 120,
  can_start,
  reason: can_start ? '' : '设备不可生产',
  review_token: 'a'.repeat(64),
});
const button = (w: ReturnType<typeof mount>, text: string) =>
  w.findAll('button').find((b) => b.text().includes(text))!;
beforeEach(() => {
  setActivePinia(createPinia());
  vi.resetAllMocks();
  useInjectionStore().factory = 'huaxing';
  useInjectionStore().machines = machines;
  api.post.mockImplementation(async (_path, data: any) => ({
    revision: 30,
    items: data.items.map((item: any) => reviewed(item.machine_id)),
    eligible_count: data.items.length,
  }));
});
afterEach(() => {
  wrappers.splice(0).forEach((w) => w.unmount());
  document.body.innerHTML = '';
});
function board(overrides = {}) {
  const w = mount(MachineBoard, {
    props: {
      machines,
      queues,
      canReport: true,
      runningOnly: false,
      filterScope: '',
      ...overrides,
    },
    attachTo: document.body,
  });
  wrappers.push(w);
  return w;
}
async function dialog() {
  const w = mount(BulkStartDialog, {
    props: {
      items: ['m0', 'm1'].map((id) => ({ machine_id: id, run_id: `r${id}` })),
      canReport: true,
    },
    attachTo: document.body,
  });
  wrappers.push(w);
  await flushPromises();
  return w;
}
it('selects all filtered candidates including cards below the fold, then reviews without starting', async () => {
  const w = board();
  await button(w, '全选待开工机台').trigger('click');
  expect(w.findAll('input.inj-machine-select:checked')).toHaveLength(76);
  expect(w.text()).toContain('已选 76 台');
  expect(api.post).not.toHaveBeenCalled();
  await button(w, '批量开工（76）').trigger('click');
  await flushPromises();
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(api.post.mock.calls[0][0]).toBe('/execution/start-preview');
  expect((api.post.mock.calls[0][1] as any).items).toHaveLength(76);
  expect(w.get('[role="dialog"]').text()).toContain('确认现在开工（76 台）');
});
it('excludes occupied, paused, down and empty machines, while retaining single start', async () => {
  const subset = machines
    .slice(0, 5)
    .map((m, i) => ({ ...m, operating_status: i === 2 ? 'FAULT' : 'IDLE' }));
  const q = {
    ...queues,
    m0: [{ ...queues.m0[0], status: 'RUNNING' }],
    m1: [{ ...queues.m1[0], status: 'PAUSED' }],
    m3: [],
  };
  const w = board({ machines: subset, queues: q });
  await button(w, '全选待开工机台').trigger('click');
  expect(w.findAll('input.inj-machine-select:checked')).toHaveLength(1);
  expect(w.text()).toContain('不可勾选：设备停机中');
  const single = w.findAll('button').find((b) => b.text() === '开工')!;
  await single.trigger('click');
  expect(w.emitted('action')).toHaveLength(1);
});
it('clears selection on filter and factory changes and prevents reportless writes', async () => {
  const w = board();
  await button(w, '全选待开工机台').trigger('click');
  await w.setProps({ filterScope: '旧车间', machines: machines.slice(0, 2) });
  expect(w.text()).toContain('已选 0 台');
  await button(w, '全选待开工机台').trigger('click');
  expect(w.text()).toContain('已选 2 台');
  useInjectionStore().factory = 'huadeng';
  await flushPromises();
  expect(w.text()).toContain('已选 0 台');
  await w.setProps({ canReport: false });
  expect(w.find('.inj-bulk-toolbar').exists()).toBe(false);
  expect(w.find('.inj-machine-select').exists()).toBe(false);
});
it('pins the selected run identity when polling changes the next batch', async () => {
  const w = board({ machines: machines.slice(0, 1) });
  await w.get('input.inj-machine-select').setValue(true);
  await w.setProps({
    queues: { ...queues, m0: [{ ...queues.m0[0], id: 'new-head' }] },
  });
  expect(w.text()).toContain('下一批已变化');
  await button(w, '批量开工（1）').trigger('click');
  await flushPromises();
  expect((api.post.mock.calls[0][1] as any).items[0].run_id).toBe('rm0');
});
it('shows partial results, removes only successes and reviews failures for retry', async () => {
  const store = useInjectionStore();
  const mutate = vi.spyOn(store, 'mutate').mockResolvedValue({
    bulk_start: true,
    results: [
      { ...reviewed('m0'), success: true, reason: '已开工' },
      { ...reviewed('m1'), success: false, reason: '设备刚刚停机' },
    ],
  });
  const w = board({ machines: machines.slice(0, 2) });
  await button(w, '全选待开工机台').trigger('click');
  await button(w, '批量开工（2）').trigger('click');
  await flushPromises();
  expect(mutate).not.toHaveBeenCalled();
  await button(w, '确认现在开工').trigger('click');
  await flushPromises();
  expect(mutate).toHaveBeenCalledWith(
    '/execution/bulk-start',
    expect.objectContaining({
      expected_revision: 30,
      confirm_actual_start: true,
    }),
  );
  expect(w.get('[role="dialog"]').text()).toContain(
    '本次已开工 1 台，1 台未开工',
  );
  expect(w.get('[role="dialog"]').text()).toContain('设备刚刚停机');
  expect(w.findAll('input.inj-machine-select:checked')).toHaveLength(1);
  await button(w, '重新核对未开工机台').trigger('click');
  await flushPromises();
  expect((api.post.mock.calls.at(-1)![1] as any).items).toEqual([
    { machine_id: 'm1', run_id: 'rm1' },
  ]);
});
it('requires resolving shared mold conflicts by removing a machine and reviewing again', async () => {
  api.post.mockResolvedValueOnce({
    revision: 30,
    eligible_count: 0,
    items: ['m0', 'm1'].map((id) => ({
      ...reviewed(id, false),
      reason: '所选机台共用同一套实物模具，请保留其中一台后重新核对',
    })),
  });
  const w = board({ machines: machines.slice(0, 2) });
  await button(w, '全选待开工机台').trigger('click');
  await button(w, '批量开工（2）').trigger('click');
  await flushPromises();
  expect(button(w, '确认现在开工').attributes('disabled')).toBeDefined();
  await w.get('button[aria-label="移除 m1"]').trigger('click');
  await flushPromises();
  expect((api.post.mock.calls.at(-1)![1] as any).items).toEqual([
    { machine_id: 'm0', run_id: 'rm0' },
  ]);
  expect(
    button(w, '确认现在开工（1 台）').attributes('disabled'),
  ).toBeUndefined();
});
it('preserves review inputs after network failure and discards a late preview on factory switch', async () => {
  const store = useInjectionStore();
  store.error = 'Network Error';
  const mutate = vi.spyOn(store, 'mutate').mockResolvedValue(null);
  const w = await dialog();
  await button(w, '确认现在开工').trigger('click');
  await button(w, '确认现在开工').trigger('click');
  expect(mutate.mock.calls[1]).toEqual(mutate.mock.calls[0]);
  expect(w.get('[role="alert"]').text()).toBe('Network Error');
  let resolve!: (value: any) => void;
  api.post.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  await button(w, '重新核对').trigger('click');
  store.factory = 'huadeng';
  await flushPromises();
  resolve({ revision: 100, items: [reviewed('FOREIGN')], eligible_count: 1 });
  await flushPromises();
  expect(w.emitted('close')).toHaveLength(1);
  expect(w.text()).not.toContain('FOREIGN');
});

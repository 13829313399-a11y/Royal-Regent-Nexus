// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { defineComponent, nextTick } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { injectionApi } from '@/api/injectionScheduling';
import { useInjectionStore } from '@/stores/injectionScheduling';
import InjSegmentedControl from '../components/ui/InjSegmentedControl.vue';
import InjButton from '../components/ui/InjButton.vue';
import MasterParameterEditor from '../components/MasterParameterEditor.vue';
import DemandDrawer from '../DemandDrawer.vue';
import MasterData from '../MasterData.vue';
import {
  createInjectionViewState,
  provideInjectionViewState,
  rowHeight,
  useInjectionViewState,
} from '../composables/useInjectionViewState';
import {
  patchJsonPath,
  patchWorkingDay,
  parseParameter,
} from '../parameterAdapter';

vi.mock('@/api/injectionScheduling', () => ({
  injectionApi: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}));
beforeEach(() => {
  setActivePinia(createPinia());
  vi.clearAllMocks();
});
afterEach(() => {
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});
const options = [
  { value: 'timeline', label: '甘特' },
  { value: 'machines', label: '看板' },
  { value: 'table', label: '计划表' },
];

describe('controlled workspace controls', () => {
  it('only moves selection after the parent accepts a request', async () => {
    const wrapper = mount(InjSegmentedControl, {
      props: { modelValue: 'timeline', options, label: '排产视图' },
    });
    await wrapper.findAll('button')[1]!.trigger('click');
    expect(wrapper.emitted('update:modelValue')).toEqual([['machines']]);
    expect(wrapper.get('[aria-pressed="true"]').text()).toBe('甘特');
    await wrapper.setProps({ modelValue: 'machines' });
    expect(wrapper.get('[aria-pressed="true"]').text()).toBe('看板');
    wrapper.unmount();
  });
  it('moves keyboard focus without triggering navigation', async () => {
    const wrapper = mount(InjSegmentedControl, {
      attachTo: document.body,
      props: { modelValue: 'timeline', options, label: '视图' },
    });
    const buttons = wrapper.findAll('button');
    (buttons[0]!.element as HTMLButtonElement).focus();
    await buttons[0]!.trigger('keydown', { key: 'ArrowRight' });
    expect(document.activeElement).toBe(buttons[1]!.element);
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    wrapper.unmount();
  });
  it('does not accept disabled transitions', async () => {
    const wrapper = mount(InjSegmentedControl, {
      props: { modelValue: 'timeline', options, label: '视图', disabled: true },
    });
    await wrapper.findAll('button')[2]!.trigger('click');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    wrapper.unmount();
  });
  it('measures accepted geometry and disconnects observers in reduced motion', async () => {
    const disconnect = vi.fn(),
      remove = vi.fn(),
      raf = vi.fn();
    vi.stubGlobal(
      'ResizeObserver',
      class {
        observe = vi.fn();
        disconnect = disconnect;
      },
    );
    vi.stubGlobal('requestAnimationFrame', raf);
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: remove,
    }));
    const wrapper = mount(InjSegmentedControl, {
      props: { modelValue: 'timeline', options, label: '视图' },
    });
    await nextTick();
    expect(wrapper.classes()).toContain('inj-no-motion');
    await wrapper.setProps({ modelValue: 'table' });
    expect(raf).not.toHaveBeenCalled();
    expect(wrapper.get('[aria-pressed="true"]').text()).toBe('计划表');
    wrapper.unmount();
    expect(disconnect).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledWith('change', expect.any(Function));
  });
  it('shows pending only from real request state and does not invent success', async () => {
    const wrapper = mount(InjButton, {
      props: { pending: false },
      slots: { default: '保存' },
    });
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(false);
    await wrapper.setProps({ pending: true });
    expect(wrapper.get('button').attributes('disabled')).toBeDefined();
    expect(wrapper.get('button').attributes('aria-busy')).toBe('true');
    await wrapper.setProps({ pending: false });
    expect(wrapper.text()).toBe('保存');
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(false);
    wrapper.unmount();
  });
});

describe('lossless parameter forms', () => {
  const original = {
    unknown: { flag: false, missing: null, zero: 0, rows: ['z', 'a'] },
    HEATING: false,
    fixtures: ['b', 'a'],
  };
  it('preserves every unknown path when one known field changes', () => {
    const next = patchJsonPath(original, ['HEATING'], true) as any;
    expect(next).toEqual({ ...original, HEATING: true });
    expect(original.HEATING).toBe(false);
    expect(next.unknown).toBe(original.unknown);
  });
  it('does not normalize array order or trailing extension values', () => {
    expect(
      patchJsonPath(
        { '5': ['43.20', '24.48', { future: null }] },
        ['5', 0],
        '44.50',
      ),
    ).toEqual({ '5': ['44.50', '24.48', { future: null }] });
    expect(patchWorkingDay([5, 0, 2], 1, true)).toEqual([5, 0, 2, 1]);
    expect(patchWorkingDay([5, 0, 2], 0, false)).toEqual([5, 2]);
  });
  it('preserves nested break metadata when changing one endpoint', () => {
    const breaks = [
      { start: '23:00', end: '01:00', metadata: { note: null, flag: false } },
    ];
    expect(patchJsonPath(breaks, [0, 'end'], '02:00')).toEqual([
      { ...breaks[0], end: '02:00' },
    ]);
  });
  it('keeps false, zero and null distinct and rejects blank numeric edits', () => {
    expect(parseParameter('false', false)).toBe(false);
    expect(parseParameter('0', 4)).toBe(0);
    expect(parseParameter('null', null)).toBeNull();
    expect(() => parseParameter('', 4)).toThrow('有效数字');
  });
  it('does not emit anything for an untouched parameter editor', async () => {
    const wrapper = mount(MasterParameterEditor, {
      props: {
        modelValue: JSON.stringify(original),
        kind: 'capabilities',
        label: '能力',
      },
    });
    await flushPromises();
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
    await wrapper.findAll('select')[1]!.setValue('true');
    const updated = JSON.parse(
      wrapper.emitted('update:modelValue')![0]![0] as string,
    );
    expect(updated).toEqual({ ...original, HEATING: true });
    wrapper.unmount();
  });
  it('round-trips complete unedited factory parameters through the existing handler', async () => {
    const parameters = {
      day_start: '08:00',
      working_days: [5, 0, 2],
      setup_interruptible: false,
      allowance_rate: 0,
      future: null,
      nested: { unknown: ['b', 'a'], flag: false },
    };
    const store = useInjectionStore();
    store.factory = 'huaxing';
    store.settings = parameters;
    vi.mocked(injectionApi.get).mockImplementation(async (path) =>
      path === '/settings' ? { parameters } : { rows: [] },
    );
    const mutate = vi.spyOn(store, 'mutate').mockResolvedValue(null);
    const wrapper = mount(MasterData, { props: { canWrite: true } });
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '排产参数')!
      .trigger('click');
    await flushPromises();
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '保存参数并重算')!
      .trigger('click');
    expect(mutate).toHaveBeenCalledWith(
      '/settings',
      { data: parameters },
      'patch',
    );
    wrapper.unmount();
  });
});

describe('inspector drafts and identity', () => {
  const field = {
    key: 'target_shots_per_day',
    label: '计划日目标',
    value_type: 'number',
    editable: true,
    group: 'process',
    legacy_column: null,
    unit: '啤',
    filter_ops: [],
  };
  it('shows batch orders individually and preserves an unknown forecast from the live run', async () => {
    const store = useInjectionStore();
    store.factory = 'huaxing';
    store.selectedId = 'one';
    store.fields = [field];
    store.detail = {
      demand: {
        id: 'one',
        mold_code: 'M',
        revision: 1,
        field_sources: {
          target_shots_per_day: { kind: 'LEGACY_CACHE', source_row: 363 },
        },
      },
      run: { id: 'run', status: 'PAUSED' },
    };
    store.runs = [
      { id: 'run', demand_ids: ['one', 'two'], forecast_unknown: true },
    ];
    vi.mocked(injectionApi.get).mockImplementation(async (path) => ({
      demand: {
        id: path.endsWith('one') ? 'one' : 'two',
        order_no: path.endsWith('one') ? 'ORDER-1' : 'ORDER-2',
        remaining_shots: path.endsWith('one') ? 368 : 450,
      },
    }));
    const wrapper = mount(DemandDrawer, {
      props: { canPlan: true, canReport: true, docked: true },
    });
    await flushPromises();
    expect(wrapper.text()).toContain('ORDER-1');
    expect(wrapper.text()).toContain('ORDER-2');
    expect(wrapper.text()).toContain('等待恢复，预计结束未知');
    expect(injectionApi.get).toHaveBeenCalledWith('/demands/two', {
      factory_id: 'huaxing',
    });
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '参数')!
      .trigger('click');
    expect(wrapper.text()).toContain('原表 · 原行 363');
    wrapper.unmount();
  });
  it('never presents the old demand as the newly selected demand', async () => {
    const store = useInjectionStore();
    store.selectedId = 'new';
    store.detail = { demand: { id: 'old', mold_code: 'OLD', revision: 1 } };
    store.fields = [field];
    const wrapper = mount(DemandDrawer, {
      props: { canPlan: true, canReport: true, docked: true },
    });
    expect(wrapper.text()).not.toContain('OLD');
    expect(wrapper.text()).toContain('正在读取所选需求');
    store.detail = { demand: { id: 'new', mold_code: 'NEW', revision: 1 } };
    await nextTick();
    expect(wrapper.text()).toContain('NEW');
    wrapper.unmount();
  });
  it('keeps one edited input alive when switching dock and overlay and blocks closing', async () => {
    const store = useInjectionStore();
    store.selectedId = 'd';
    store.fields = [field];
    store.detail = {
      demand: {
        id: 'd',
        mold_code: 'M',
        revision: 1,
        target_shots_per_day: 100,
      },
    };
    const wrapper = mount(DemandDrawer, {
      props: { canPlan: true, canReport: true, docked: true },
    });
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '参数')!
      .trigger('click');
    const input = wrapper.get('input');
    await input.setValue('250');
    await wrapper.setProps({ docked: false });
    expect(wrapper.get('input').element).toBe(input.element);
    expect((input.element as HTMLInputElement).value).toBe('250');
    expect(wrapper.get('aside').attributes('aria-modal')).toBe('true');
    await wrapper.get('[aria-label="关闭详情"]').trigger('click');
    expect(wrapper.emitted('close')).toBeUndefined();
    expect(store.dirty).toBe(true);
    await wrapper.setProps({ docked: true });
    expect(wrapper.get('aside').attributes('aria-modal')).toBeUndefined();
    await wrapper.get('aside').trigger('keydown', { key: 'Tab' });
    expect(wrapper.get('input').element).toBe(input.element);
    wrapper.unmount();
  });
  it('omits report and edit actions for read-only users', () => {
    const store = useInjectionStore();
    store.selectedId = 'd';
    store.detail = {
      demand: { id: 'd', revision: 1 },
      run: { status: 'RUNNING' },
    };
    store.fields = [field];
    const wrapper = mount(DemandDrawer, {
      props: { canPlan: false, canReport: false, docked: true },
    });
    expect(wrapper.findAll('button').map((b) => b.text())).not.toContain(
      '保存参数并重算',
    );
    wrapper.unmount();
  });
});

it('does not render an earlier master category while a new category loads or fails', async () => {
  const store = useInjectionStore();
  store.factory = 'huaxing';
  let rejectMachine!: (error: Error) => void;
  vi.mocked(injectionApi.get).mockImplementation(async (path) =>
    path === '/machines'
      ? new Promise((_resolve, reject) => {
          rejectMachine = reject;
        })
      : { rows: [{ id: 'mold', mold_code: 'SHARED-MOLD' }] },
  );
  const wrapper = mount(MasterData, { props: { canWrite: true } });
  await flushPromises();
  expect(wrapper.text()).toContain('SHARED-MOLD');
  await wrapper
    .findAll('button')
    .find((b) => b.text() === '本厂设备')!
    .trigger('click');
  expect(wrapper.text()).toContain('正在读取基础资料');
  expect(wrapper.text()).not.toContain('SHARED-MOLD');
  rejectMachine(new Error('network unavailable'));
  await flushPromises();
  expect(wrapper.text()).toContain('资料读取失败');
  expect(wrapper.text()).not.toContain('暂无资料');
  wrapper.unmount();
});

it('keeps display state for remounted views without global or persisted state', async () => {
  let parentState: ReturnType<typeof createInjectionViewState> | undefined;
  const Child = defineComponent({
    setup() {
      const view = useInjectionViewState();
      return { view };
    },
    template: '<span>{{view.zoom}} {{view.poolWidth}}</span>',
  });
  const Parent = defineComponent({
    components: { Child },
    setup() {
      parentState = provideInjectionViewState();
      return { view: parentState };
    },
    template: '<Child v-if="!view.focusMode" />',
  });
  const wrapper = mount(Parent);
  parentState!.zoom = 'hour';
  parentState!.poolWidth = 312;
  parentState!.focusMode = true;
  await nextTick();
  parentState!.focusMode = false;
  await nextTick();
  expect(wrapper.text()).toBe('hour 312');
  wrapper.unmount();
  expect(createInjectionViewState(390).planningView).toBe('machines');
  expect(createInjectionViewState(1920).poolWidth).toBe(264);
  expect(rowHeight('comfortable', 'table')).toBe(44);
  expect(rowHeight('comfortable', 'timeline')).toBe(80);
  expect(rowHeight('compact', 'table')).toBe(36);
  expect(rowHeight('compact', 'timeline')).toBe(64);
});

// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { defineComponent, nextTick, shallowRef } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { useInjectionStore } from '@/stores/injectionScheduling';
import PlanTable from '../PlanTable.vue';
import { provideInjectionViewState, type InjectionViewState } from '../composables/useInjectionViewState';

vi.mock('@/api/injectionScheduling', () => ({ injectionApi: {} }));
vi.mock('@tanstack/vue-virtual', () => ({
  useVirtualizer: () => shallowRef({ getVirtualItems: () => [], getTotalSize: () => 0, measure: vi.fn() }),
}));
let width = 1200;
let resize: () => void;
const disconnect = vi.fn();
beforeEach(() => {
  setActivePinia(createPinia());
  width = 1200;
  disconnect.mockClear();
  vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width);
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback; }
    observe() {}
    disconnect = disconnect;
  });
  useInjectionStore().fields = ['machine_code', 'mold_code', 'remaining_shots'].map(key => ({
    key, label: key, value_type: 'number', editable: false, group: 'quantity', filter_ops: [],
  }));
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it('keeps a scrollable area on narrow viewports and restores the saved freeze count on widening', async () => {
  let view!: InjectionViewState;
  const wrapper = mount(defineComponent({
    components: { PlanTable },
    setup() { view = provideInjectionViewState(); },
    template: '<PlanTable :can-edit="false" />',
  }));
  await nextTick();
  const headers = () => wrapper.findAll('thead th').slice(1);
  const scroller = wrapper.get('.inj-grid-scroll').element as HTMLElement;
  expect(headers().map(h => (h.element as HTMLElement).style.position)).toEqual(['sticky', 'sticky', '']);
  width = 342; resize(); await nextTick();
  expect(headers().map(h => (h.element as HTMLElement).style.position)).toEqual(['sticky', '', '']);
  expect((wrapper.get('.inj-grid-scroll').element as HTMLElement).style.scrollPaddingInlineStart).toBe('171px');
  width = 240; resize(); await nextTick();
  expect(headers().map(h => (h.element as HTMLElement).style.position)).toEqual(['', '', '']);
  scroller.scrollLeft = 1000;
  width = 1200; resize(); await nextTick();
  expect(headers().map(h => (h.element as HTMLElement).style.position)).toEqual(['sticky', 'sticky', '']);
  expect(scroller.scrollLeft).toBe(697);
  width = 342; resize(); await nextTick();
  expect(scroller.scrollLeft).toBe(875);
  wrapper.unmount();
  expect(view.table?.freeze).toBe(2);
  expect(disconnect).toHaveBeenCalledOnce();
});

it('disconnects the viewport observer even when the factory context has already changed', async () => {
  let view!: InjectionViewState;
  const wrapper = mount(defineComponent({
    components: { PlanTable },
    setup() { view = provideInjectionViewState(); },
    template: '<PlanTable :can-edit="false" />',
  }));
  view.contextGeneration++;
  wrapper.unmount();
  expect(disconnect).toHaveBeenCalledOnce();
  expect(view.table).toBeNull();
});

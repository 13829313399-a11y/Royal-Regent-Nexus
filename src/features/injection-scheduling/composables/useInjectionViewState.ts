import { inject, provide, reactive, type InjectionKey } from 'vue';

export function createInjectionViewState(width = 1440) {
  return reactive({
    contextGeneration: 0,
    poolEntered: false,
    planningView: width < 760 ? 'machines' : 'timeline',
    density: 'compact' as 'compact' | 'comfortable',
    poolExpanded: true,
    poolWidth: 264,
    inspectorExpanded: false,
    focusMode: false,
    zoom: 'shift',
    date: new Date().toLocaleDateString('en-CA'),
    workshop: '',
    machineSearch: '',
    scroll: {} as Record<string, { top: number; left: number }>,
    table: null as null | {
      preset: string;
      sizing: Record<string, number>;
      visibility: Record<string, boolean>;
      order: string[];
      freeze: number;
    },
  });
}
export type InjectionViewState = ReturnType<typeof createInjectionViewState>;
const key: InjectionKey<InjectionViewState> = Symbol('injection-view-state');
export function provideInjectionViewState() {
  const state = createInjectionViewState(
    typeof window === 'undefined' ? 1440 : window.innerWidth,
  );
  provide(key, state);
  return state;
}
export function useInjectionViewState() {
  return inject(key, createInjectionViewState, true);
}
export const rowHeight = (density: string, kind: 'table' | 'timeline') =>
  kind === 'table'
    ? density === 'comfortable'
      ? 44
      : 36
    : density === 'comfortable'
      ? 80
      : 64;

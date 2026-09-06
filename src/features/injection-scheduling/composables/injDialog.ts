import { nextTick, type ObjectDirective } from 'vue';

type DialogBinding = { close: () => void; busy?: boolean };
const instances = new WeakMap<
  HTMLElement,
  {
    previous: HTMLElement | null;
    keydown: (event: KeyboardEvent) => void;
    value: DialogBinding;
    disposed: boolean;
  }
>();
export const vInjDialog: ObjectDirective<HTMLElement, DialogBinding> = {
  mounted(element, binding) {
    const state = {
      previous: document.activeElement as HTMLElement | null,
      value: binding.value,
      disposed: false,
      keydown(event: KeyboardEvent) {
        if (event.isComposing) return;
        if (event.key === 'Escape') {
          event.stopPropagation();
          if (!state.value.busy) state.value.close();
          return;
        }
        if (event.key !== 'Tab') return;
        const controls = Array.from(
          element.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), summary, [tabindex="0"]',
          ),
        ).filter(
          (node) => node.getClientRects().length && !node.closest('[inert]'),
        );
        const first = controls[0],
          last = controls.at(-1);
        if (!first) {
          event.preventDefault();
          element.focus();
          return;
        }
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === element)
        ) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      },
    };
    instances.set(element, state);
    element.tabIndex = -1;
    element.addEventListener('keydown', state.keydown);
    nextTick(() => {
      if (!state.disposed) element.focus();
    });
  },
  updated(element, binding) {
    const state = instances.get(element);
    if (state) state.value = binding.value;
  },
  beforeUnmount(element) {
    const state = instances.get(element);
    if (!state) return;
    state.disposed = true;
    element.removeEventListener('keydown', state.keydown);
    if (state.previous?.isConnected) state.previous.focus();
    instances.delete(element);
  },
};

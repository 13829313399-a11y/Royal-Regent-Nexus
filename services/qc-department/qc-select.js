const dropdowns = 'select:not([multiple], [size]:not([size="1"], [size="0"]))';

export function mountQcSelects(scope) {
  const document = scope.ownerDocument;
  const view = document.defaultView;
  if (!view?.CSS?.supports('appearance: base-select') ||
      !view.CSS.supports('selector(select::picker(select))') ||
      !view.CSS.supports('selector(select:open)') ||
      view.matchMedia('(forced-colors: active)').matches) return () => {};

  let frame = 0;
  let dirty = true;
  let mounted = true;

  function update() {
    frame = 0;
    if (scope.querySelector('select[data-qc-picker]:open')) return;
    dirty = false;
    const selects = [...scope.querySelectorAll('select')];
    for (const select of selects) select.removeAttribute('data-qc-picker');
    // Measure the native boxes together. Customizable selects otherwise resize
    // to the current option, shifting controls that originally fit all options.
    const sizes = selects.map(select => {
      if (!select.matches(dropdowns) || !select.getClientRects().length) return null;
      const style = view.getComputedStyle(select);
      return { width:style.width, height:style.height };
    });
    for (const [index, select] of selects.entries()) {
      const size = sizes[index];
      select.toggleAttribute('data-qc-picker', Boolean(size));
      if (!size) continue;
      select.style.setProperty('--qc-select-width', size.width);
      select.style.setProperty('--qc-select-height', size.height);
    }
    observer.takeRecords();
  }

  function schedule() {
    if (mounted && dirty && !frame) frame = view.requestAnimationFrame(update);
  }
  function invalidate() {
    dirty = true;
    schedule();
  }
  const containsSelect = element => element?.nodeType === 1 &&
    (element.matches('select') || element.querySelector('select'));
  const observer = new view.MutationObserver(changes => {
    if (changes.some(change => {
      const element = change.target.nodeType === 1 ? change.target : change.target.parentElement;
      return element?.closest('select') ||
        (change.type === 'attributes' && containsSelect(element)) ||
        [...change.addedNodes, ...change.removedNodes].some(containsSelect);
    })) invalidate();
  });
  observer.observe(scope, {
    childList:true, subtree:true, characterData:true, attributes:true,
    attributeFilter:['class', 'style', 'hidden', 'open', 'disabled', 'multiple', 'size', 'label', 'selected'],
  });
  view.addEventListener('resize', invalidate);
  function changeSelection(event) {
    if (event.target.matches?.(dropdowns)) invalidate();
  }
  scope.addEventListener('change', changeSelection);
  for (const event of ['keydown', 'pointerup', 'focusout']) scope.addEventListener(event, schedule, true);
  document.fonts?.ready.then(invalidate);
  update();

  return () => {
    mounted = false;
    observer.disconnect();
    view.cancelAnimationFrame(frame);
    view.removeEventListener('resize', invalidate);
    scope.removeEventListener('change', changeSelection);
    for (const event of ['keydown', 'pointerup', 'focusout']) scope.removeEventListener(event, schedule, true);
    for (const select of scope.querySelectorAll('select[data-qc-picker]')) {
      select.removeAttribute('data-qc-picker');
      select.style.removeProperty('--qc-select-width');
      select.style.removeProperty('--qc-select-height');
    }
  };
}

if (typeof document !== 'undefined' && document.body?.classList.contains('qc-liquid-glass')) {
  mountQcSelects(document.body);
}

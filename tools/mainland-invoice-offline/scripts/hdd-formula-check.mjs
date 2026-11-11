/** Independent evaluator for formulas emitted by the invoice generator. */
export function evaluateInvoiceCell(wb, sheetName, address, active = new Set()) {
  const key = `${sheetName}!${address}`;
  if (active.has(key)) throw new Error(`Circular formula at ${key}`);
  const ws = wb.Sheets[sheetName];
  if (!ws) throw new Error(`Missing referenced sheet ${sheetName}`);
  const cell = ws[address];
  if (!cell?.f) return typeof cell?.v === 'number' ? cell.v : 0;
  const stack = new Set(active).add(key);
  const read = (target, ref) => evaluateInvoiceCell(wb, target, ref.replace(/\$/g, ''), stack);
  let expression = cell.f.replace(/^=/, '');
  expression = expression.replace(/SUM\(\$?([A-Z]+)\$?(\d+):\$?\1\$?(\d+)\)/gi,
    (_, col, from, to) => {
      let sum = 0;
      for (let row = +from; row <= +to; row++) sum += read(sheetName, `${col}${row}`);
      return `(${sum})`;
    });
  expression = expression.replace(/(?:'((?:[^']|'')+)'!)?(\$?[A-Z]+\$?\d+)/g,
    (_, quoted, ref) => `(${read(quoted == null ? sheetName : quoted.replace(/''/g, "'"), ref)})`);
  if (!/^[\d.eE+\-*/()\s]+$/.test(expression)) {
    throw new Error(`Unsupported or invalid formula at ${key}: ${cell.f}`);
  }
  // Parse numbers and elementary arithmetic without eval or cached dependency values.
  const tokens = expression.match(/(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?|[()+\-*/]/gi) ?? [];
  let cursor = 0;
  function atom() {
    const token = tokens[cursor++];
    if (token === '+') return atom();
    if (token === '-') return -atom();
    if (token === '(') {
      const result = add();
      if (tokens[cursor++] !== ')') throw new Error(`Unbalanced formula at ${key}`);
      return result;
    }
    const result = Number(token);
    if (!Number.isFinite(result)) throw new Error(`Invalid number at ${key}`);
    return result;
  }
  function multiply() {
    let result = atom();
    while (tokens[cursor] === '*' || tokens[cursor] === '/') {
      const op = tokens[cursor++];
      result = op === '*' ? result * atom() : result / atom();
    }
    return result;
  }
  function add() {
    let result = multiply();
    while (tokens[cursor] === '+' || tokens[cursor] === '-') {
      const op = tokens[cursor++];
      result = op === '+' ? result + multiply() : result - multiply();
    }
    return result;
  }
  const result = add();
  if (cursor !== tokens.length) throw new Error(`Trailing formula tokens at ${key}`);
  return result;
}


/** Check every cached formula against an independent calculation, including its dependencies. */
export function auditInvoiceFormulaCaches(wb, { tolerance = 1e-7 } = {}) {
  let checked = 0;
  const mismatches = [];
  for (const sheetName of wb.SheetNames) {
    for (const [address, cell] of Object.entries(wb.Sheets[sheetName])) {
      if (!cell?.f) continue;
      checked++;
      try {
        const actual = evaluateInvoiceCell(wb, sheetName, address);
        if (typeof cell.v !== 'number' || !Number.isFinite(actual) || Math.abs(actual - cell.v) > tolerance) {
          mismatches.push({ sheetName, address, formula: cell.f, cached: cell.v, calculated: actual });
        }
      } catch (error) {
        mismatches.push({ sheetName, address, formula: cell.f, cached: cell.v, error: error.message });
      }
    }
  }
  return { checked, mismatches };
}

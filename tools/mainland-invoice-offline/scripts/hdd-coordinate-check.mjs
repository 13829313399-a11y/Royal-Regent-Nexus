/** Independent OOXML coordinate audit; does not use the production row parser. */
import JSZip from 'jszip';

export async function auditWorkbookCoordinates(buffer) {
  const zip = await JSZip.loadAsync(buffer);
  const issues = [];
  let sheets = 0, rows = 0, cells = 0;
  for (const name of Object.keys(zip.files).filter((path) => /^xl\/worksheets\/[^/]+\.xml$/.test(path))) {
    sheets++;
    const xml = await zip.file(name).async('string');
    const rowNumbers = new Set();
    let containedCells = 0;
    for (const match of xml.matchAll(/<(?:\w+:)?row\b([^>]*?)(?:\/>|>([\s\S]*?)<\/(?:\w+:)?row>)/g)) {
      rows++;
      const rowText = match[1].match(/\br="([^"]+)"/)?.[1];
      const row = Number(rowText);
      if (!/^\d+$/.test(rowText ?? '') || row < 1 || row > 1048576) {
        issues.push({ sheet: name, row: rowText, reason: 'invalid parent row number' });
      }
      if (rowNumbers.has(row)) issues.push({ sheet: name, row, reason: 'duplicate row number' });
      rowNumbers.add(row);
      const refs = new Set();
      for (const cell of (match[2] ?? '').matchAll(/<(?:\w+:)?c\b([^>]*?)(?:\/>|>)/g)) {
        cells++;
        containedCells++;
        const ref = cell[1].match(/\br="([^"]+)"/)?.[1];
        const coordinate = ref?.match(/^([A-Z]+)(\d+)$/);
        if (!coordinate) {
          issues.push({ sheet: name, row, ref, reason: 'invalid cell coordinate' });
          continue;
        }
        const column = [...coordinate[1]].reduce((value, ch) => value * 26 + ch.charCodeAt(0) - 64, 0);
        if (column > 16384) issues.push({ sheet: name, row, ref, reason: 'column exceeds Excel limit' });
        if (+coordinate[2] !== row) issues.push({ sheet: name, row, ref, reason: 'cell row differs from parent row' });
        if (refs.has(ref)) issues.push({ sheet: name, row, ref, reason: 'duplicate cell coordinate' });
        refs.add(ref);
      }
    }
    const allCells = [...xml.matchAll(/<(?:\w+:)?c\b/g)].length;
    if (containedCells !== allCells) issues.push({ sheet: name, reason: 'cells found outside parsed rows' });
  }
  if (!sheets) issues.push({ reason: 'workbook has no worksheet XML' });
  return { sheets, rows, cells, issues };
}

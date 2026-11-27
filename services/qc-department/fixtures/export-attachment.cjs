const { zipSync, strToU8 } = require('fflate');

module.exports = function attachment(window, extension) {
  const bytes = extension === 'xlsx'
    ? zipSync({ 'xl/workbook.xml': strToU8('<workbook/>') })
    : new Uint8Array(1024);
  if (extension === 'xls') bytes.set([0xd0, 0xcf, 0x11, 0xe0, 0xa1, 0xb1, 0x1a, 0xe1]);
  window.URL.createObjectURL = () => 'blob:verified-attachment';
  window.URL.revokeObjectURL = () => {};
  return new Response(bytes, { headers: {
    'Content-Disposition': 'attachment',
    'Content-Type': extension === 'xlsx'
      ? 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      : 'application/vnd.ms-excel',
  } });
};

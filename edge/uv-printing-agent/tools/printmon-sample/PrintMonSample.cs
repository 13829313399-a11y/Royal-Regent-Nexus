using System;
using System.Collections.Generic;
using System.Drawing;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

namespace RoyalRegent.Uv
{
    public static class PrintMonSample
    {
        internal const string NexusUnknown = "尚未测试";
        internal const string NexusOk = "已打开 Nexus 登录页或工作台";
        internal const string NexusFailed = "未能打开 Nexus";
        private static readonly Regex DailyLog = new Regex(@"^(0[1-9]|[12][0-9]|3[01])_log(?:\.txt)?$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        private static readonly Regex MonthFolder = new Regex(@"^\d{4}_(?:0[1-9]|1[0-2])$");

        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new SampleForm());
        }

        public static string WindowsDescription()
        {
            using (var key = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\Microsoft\Windows NT\CurrentVersion"))
            {
                if (key == null) return Environment.OSVersion.VersionString;
                string product = Convert.ToString(key.GetValue("ProductName"));
                string build = Convert.ToString(key.GetValue("CurrentBuildNumber"));
                int number;
                // Windows 11 can retain a Windows 10 ProductName in this registry key.
                if (product.StartsWith("Windows 10", StringComparison.Ordinal) &&
                    int.TryParse(build, out number) && number >= 22000)
                    product = "Windows 11" + product.Substring("Windows 10".Length);
                return string.Format("{0} {1} (Build {2}) {3} 位", product,
                    key.GetValue("DisplayVersion") ?? key.GetValue("ReleaseId"), build,
                    Environment.Is64BitOperatingSystem ? 64 : 32);
            }
        }

        internal static DateTime ReadMoment(DateTime day, string time)
        {
            DateTime value;
            if (!DateTime.TryParseExact(day.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) + " " + time.Trim(),
                new[] { "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd HH:mm" },
                CultureInfo.InvariantCulture, DateTimeStyles.None, out value))
                throw new ArgumentException("请按“年-月-日 时:分:秒”填写开始和结束时间。");
            return DateTime.SpecifyKind(value, DateTimeKind.Unspecified);
        }

        public static string Save(string[] logs, string job, DateTime start, DateTime finish,
            string nexus, string note, string folder)
        {
            if (logs == null || logs.Length == 0 || logs.Length > 2)
                throw new ArgumentException("请选择本单的一个原始日志文件，跨日时可添加第二个。");
            if (string.IsNullOrWhiteSpace(job)) throw new ArgumentException("请填写 Print Mon 中显示的打印文件名。");
            if (start > finish) throw new ArgumentException("结束时间早于开始时间，请核对日期与时间。");
            if (nexus != NexusOk && nexus != NexusFailed && nexus != NexusUnknown)
                throw new ArgumentException("请选择这台电脑实际打开 Nexus 的结果。");
            string packet = "UV06-" + DateTime.Now.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 12);
            string destination = Path.Combine(folder, "UV6号机-回传-" + packet.Substring(5) + ".zip");
            string temporary = Path.Combine(folder, packet + ".partial");
            var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var files = new List<object>();
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                try
                {
                    using (var archive = new ZipArchive(output, ZipArchiveMode.Create, true, Encoding.UTF8))
                    {
                        foreach (string selected in logs)
                        {
                            string path = Path.GetFullPath(selected);
                            string name = Path.GetFileName(path);
                            if (!DailyLog.IsMatch(name)) throw new ArgumentException("请选择按天命名的日志，例如 09_log.txt 或 09_log。");
                            if (!paths.Add(path)) throw new ArgumentException("同一份日志已选两次，请移除重复项。");
                            string parent = new DirectoryInfo(Path.GetDirectoryName(path)).Name;
                            string month = MonthFolder.IsMatch(parent) ? parent : null;
                            string entryName = "logs/" + (files.Count + 1) + "/" + (month == null ? "" : month + "/") + name;
                            files.Add(CopyLog(archive, path, entryName, name, month));
                        }
                        var metadata = new
                        {
                            schema_version = 1, machine_code = "UV-06", machine_name = "6号机",
                            registered_model = "盛煌科 SHK-1612", registered_software = "Print Mon 7.5.79",
                            windows = WindowsDescription(), time_zone = TimeZoneInfo.Local.Id,
                            collected_at = DateTimeOffset.Now.ToString("o", CultureInfo.InvariantCulture),
                            operator_observation = new {
                                file_name = Path.GetFileName(job.Trim()), started_local = new DateTimeOffset(start).ToString("o"),
                                finished_local = new DateTimeOffset(finish).ToString("o"), nexus_browser_result = nexus,
                                note = (note ?? "").Trim()
                            }, logs = files
                        };
                        using (var writer = new StreamWriter(archive.CreateEntry("现场记录.json").Open(), new UTF8Encoding(false)))
                            writer.Write(new JavaScriptSerializer().Serialize(metadata));
                    }
                    output.Flush(true);
                }
                catch
                {
                    output.Close();
                    File.Delete(temporary);
                    throw;
                }
            }
            try { File.Move(temporary, destination); }
            finally { if (File.Exists(temporary)) File.Delete(temporary); }
            return destination;
        }

        private static object CopyLog(ZipArchive archive, string path, string entryName, string name, string month)
        {
            // Use the initial length so an actively appended log yields a bounded, byte-exact prefix.
            using (var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
            using (var sha = SHA256.Create())
            {
                long size = input.Length;
                if (size == 0) throw new InvalidDataException(name + " 为空。请在正常完工后选择有内容的原始日志。");
                long remaining = size;
                var buffer = new byte[65536];
                using (var entry = archive.CreateEntry(entryName, CompressionLevel.Fastest).Open())
                {
                    while (remaining > 0)
                    {
                        int read = input.Read(buffer, 0, (int)Math.Min(buffer.Length, remaining));
                        if (read == 0) throw new EndOfStreamException(name + " 在读取时缩短。请重新选择完整日志。");
                        sha.TransformBlock(buffer, 0, read, null, 0);
                        entry.Write(buffer, 0, read);
                        remaining -= read;
                    }
                }
                sha.TransformFinalBlock(new byte[0], 0, 0);
                return new { archive_entry = entryName, original_name = name, month_folder = month,
                    bytes = size, sha256 = BitConverter.ToString(sha.Hash).Replace("-", "").ToLowerInvariant() };
            }
        }
    }

    internal sealed class SampleForm : Form
    {
        private readonly ListBox logs = new ListBox { Dock = DockStyle.Fill, Height = 54, HorizontalScrollbar = true };
        private readonly TextBox job = new TextBox { Dock = DockStyle.Fill, MaxLength = 260, AccessibleName = "打印文件名" };
        private readonly DateTimePicker date = new DateTimePicker { Format = DateTimePickerFormat.Custom, CustomFormat = "yyyy-MM-dd", Width = 136, AccessibleName = "开工日期" };
        private readonly TextBox start = new TextBox { Width = 108, MaxLength = 8, AccessibleName = "现场开始时间" };
        private readonly TextBox finish = new TextBox { Width = 108, MaxLength = 8, AccessibleName = "现场结束时间" };
        private readonly CheckBox nextDay = new CheckBox { AutoSize = true, Text = "次日完工" };
        private readonly ComboBox nexus = new ComboBox { Dock = DockStyle.Fill, DropDownStyle = ComboBoxStyle.DropDownList, AccessibleName = "浏览器打开 Nexus" };
        private readonly TextBox note = new TextBox { Dock = DockStyle.Fill, MaxLength = 512, AccessibleName = "现场备注" };
        private readonly Label result = new Label { Dock = DockStyle.Fill, AutoSize = true, MaximumSize = new Size(650, 0) };
        private readonly Button save = new Button { Text = "生成回传 ZIP", AutoSize = true };
        private readonly TableLayoutPanel layout = new TableLayoutPanel { ColumnCount = 2, Dock = DockStyle.Top, AutoSize = true, Padding = new Padding(15) };
        private bool saving;

        internal SampleForm()
        {
            Text = "6号机 · Print Mon 现场取样";
            Font = new Font("Microsoft YaHei UI", 9F);
            AutoScaleMode = AutoScaleMode.Dpi;
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(710, 476);
            MinimumSize = new Size(570, 400);
            AutoScroll = true;
            Controls.Add(layout);
            FormClosing += delegate(object sender, FormClosingEventArgs e) { if (saving) e.Cancel = true; };
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
            layout.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
            AddRow("机台", new Label { AutoSize = true, Text = "华康 A · 6号机 · 盛煌科 SHK-1612" });
            AddRow("控制电脑", new Label { AutoSize = true, Text = PrintMonSample.WindowsDescription() });
            var add = new Button { Text = "选择当日日志…", AutoSize = true };
            var remove = new Button { Text = "移除选中项", AutoSize = true };
            add.Click += delegate { SelectLogs(); };
            remove.Click += delegate { if (logs.SelectedIndex >= 0) logs.Items.RemoveAt(logs.SelectedIndex); };
            AddRow("Print Mon 日志", Line(add, remove));
            AddRow("", logs);
            AddRow("打印文件名", job);
            AddRow("开工日期", date);
            AddRow("现场实际时间", Line(new Label { Text = "开始", AutoSize = true }, start,
                new Label { Text = "结束", AutoSize = true }, finish, nextDay));
            AddRow("", new Label { AutoSize = true, Text = "按控制电脑的时间填写，例如 08:35:12。精确到分钟也可填 08:35。" });
            nexus.Items.AddRange(new object[] { PrintMonSample.NexusUnknown, PrintMonSample.NexusOk, PrintMonSample.NexusFailed });
            nexus.SelectedIndex = 0;
            AddRow("浏览器打开 Nexus", nexus);
            AddRow("现场备注（可选）", note);
            save.Click += async delegate { await SavePacket(); };
            AddRow("", save);
            AddRow("", result);
        }

        private static FlowLayoutPanel Line(params Control[] controls)
        {
            var panel = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, Margin = Padding.Empty };
            panel.Controls.AddRange(controls);
            return panel;
        }

        private void AddRow(string caption, Control control)
        {
            int row = layout.RowCount++;
            layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            layout.Controls.Add(new Label { Text = caption, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(3, 5, 14, 5) }, 0, row);
            layout.Controls.Add(control, 1, row);
        }

        private void SelectLogs()
        {
            using (var picker = new OpenFileDialog { Title = "选择 KnfunLog 下所需日期的 DD_log.txt 或 DD_log",
                Filter = "Print Mon 日志|??_log.txt;??_log|所有文件|*.*", Multiselect = true })
            {
                if (picker.ShowDialog(this) != DialogResult.OK) return;
                foreach (string item in picker.FileNames)
                {
                    if (logs.Items.Contains(item)) continue;
                    if (logs.Items.Count == 2) { MessageBox.Show(this, "一单最多选两份跨日日志。"); break; }
                    logs.Items.Add(item);
                }
            }
        }

        private async Task SavePacket()
        {
            try
            {
                DateTime day = date.Value.Date;
                DateTime began = PrintMonSample.ReadMoment(day, start.Text);
                DateTime ended = PrintMonSample.ReadMoment(day.AddDays(nextDay.Checked ? 1 : 0), finish.Text);
                if (logs.Items.Count == 0 || string.IsNullOrWhiteSpace(job.Text) || ended < began)
                    throw new ArgumentException("请选择日志、填写打印文件名，并核对起止时间及“次日完工”。");
                string[] selected = new string[logs.Items.Count];
                logs.Items.CopyTo(selected, 0);
                string filename = job.Text, network = (string)nexus.SelectedItem, remarks = note.Text;
                using (var picker = new FolderBrowserDialog { Description = "选择存放回传 ZIP 的文件夹",
                    SelectedPath = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory) })
                {
                    if (picker.ShowDialog(this) != DialogResult.OK) return;
                    string folder = picker.SelectedPath;
                    saving = true;
                    layout.Enabled = false;
                    UseWaitCursor = true;
                    string packet = await Task.Run(() => PrintMonSample.Save(selected, filename, began, ended, network, remarks, folder));
                    result.Text = "已生成 " + packet;
                    MessageBox.Show(this, "请把下面的 ZIP 发给联调人员：\n\n" + packet, "取样完成", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            }
            catch (Exception error) { result.Text = error.Message; MessageBox.Show(this, error.Message, "取样提示"); }
            finally { saving = false; layout.Enabled = true; UseWaitCursor = false; }
        }
    }
}

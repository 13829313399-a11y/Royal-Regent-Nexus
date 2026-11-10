using System;
using System.Net;
using System.Net.Sockets;

public sealed class WiredProbeResult {
    public string status = "failed";
    public string error = "";
    public bool interface_forced;
    public string source_ip = "";
}

public static class RRWiredProbe {
    public static WiredProbeResult Check(string source, int index, string target, int port, int timeoutMs) {
        var result = new WiredProbeResult();
        using (var client = new TcpClient(AddressFamily.InterNetwork)) {
            try {
                // Windows IP_UNICAST_IF takes an interface index in network byte order.
                var option = (SocketOptionName)31;
                var encoded = IPAddress.HostToNetworkOrder(index);
                client.Client.SetSocketOption(SocketOptionLevel.IP, option, encoded);
                var actual = (int)client.Client.GetSocketOption(SocketOptionLevel.IP, option);
                // Getsockopt returns the interface index in host byte order.
                if (actual != index) { result.error = "interface_binding_unverified"; return result; }
                result.interface_forced = true;
                client.Client.Bind(new IPEndPoint(IPAddress.Parse(source), 0));
                var task = client.ConnectAsync(IPAddress.Parse(target), port);
                if (!task.Wait(timeoutMs)) { result.error = "timeout"; return result; }
                task.GetAwaiter().GetResult();
                result.source_ip = ((IPEndPoint)client.Client.LocalEndPoint).Address.ToString();
                if (result.source_ip != source) { result.error = "unexpected_source"; return result; }
                result.status = "ok";
            } catch (Exception e) {
                while (e is AggregateException && e.InnerException != null) e = e.InnerException;
                var socketError = e as SocketException;
                result.error = socketError == null ? e.GetType().Name : socketError.SocketErrorCode.ToString();
            }
        }
        return result;
    }
}

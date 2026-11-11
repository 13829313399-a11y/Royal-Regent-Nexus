using System;
using System.Net;
using System.Runtime.InteropServices;

public static class RRLinkAddress {
    [DllImport("iphlpapi.dll", ExactSpelling=true)]
    static extern uint SendARP(uint destination, uint source, [Out] byte[] buffer, ref uint length);
    public sealed class Result {
        public uint code;
        public string mac;
    }
    public static Result Lookup(string source, string destination) {
        byte[] buffer = new byte[8];
        uint length = (uint)buffer.Length;
        uint from = BitConverter.ToUInt32(IPAddress.Parse(source).GetAddressBytes(), 0);
        uint to = BitConverter.ToUInt32(IPAddress.Parse(destination).GetAddressBytes(), 0);
        uint code = SendARP(to, from, buffer, ref length);
        return new Result {
            code = code,
            mac = code == 0 && length == 6 ? BitConverter.ToString(buffer, 0, 6) : null
        };
    }
}
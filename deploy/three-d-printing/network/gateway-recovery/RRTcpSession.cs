using System;
using System.ComponentModel;
using System.Net;
using System.Runtime.InteropServices;

public static class RRTcpSession {
    const int OwnerPidAll = 5;
    const uint Established = 5;
    const uint DeleteTcb = 12;
    [StructLayout(LayoutKind.Sequential)]
    struct TcpRow {
        public uint State, LocalAddress, LocalPort, RemoteAddress, RemotePort;
    }
    [StructLayout(LayoutKind.Sequential)]
    struct OwnedRow {
        public TcpRow Row;
        public uint OwnerPid;
    }
    [DllImport("iphlpapi.dll", ExactSpelling=true)]
    static extern uint GetExtendedTcpTable(IntPtr table, ref int size, bool sorted, int family, int tableClass, uint reserved);
    [DllImport("iphlpapi.dll", ExactSpelling=true)]
    static extern uint SetTcpEntry(ref TcpRow row);
    static uint Address(string ip) {
        var bytes = IPAddress.Parse(ip).GetAddressBytes();
        if (bytes.Length != 4) throw new ArgumentException("IPv4 required");
        return BitConverter.ToUInt32(bytes,0);
    }
    static uint Port(int port) {
        if (port < 1 || port > 65535) throw new ArgumentOutOfRangeException("port");
        return (ushort)IPAddress.HostToNetworkOrder(unchecked((short)port));
    }
    static bool Find(string local, int lport, string target, int rport, int pid, out TcpRow match) {
        uint la=Address(local), ra=Address(target), lp=Port(lport), rp=Port(rport);
        match = new TcpRow();
        int size=0;
        uint code=GetExtendedTcpTable(IntPtr.Zero,ref size,false,2,OwnerPidAll,0);
        if (code!=122 && code!=0) throw new Win32Exception((int)code);
        for (int retry=0; retry<3; retry++) {
            int allocated=size;
            IntPtr table=Marshal.AllocHGlobal(Math.Max(allocated,4));
            try {
                code=GetExtendedTcpTable(table,ref size,false,2,OwnerPidAll,0);
                if (code==122) continue;
                if (code!=0) throw new Win32Exception((int)code);
                int count=Marshal.ReadInt32(table), stride=Marshal.SizeOf(typeof(OwnedRow));
                if (count<0 || 4L+(long)count*stride>allocated) throw new InvalidOperationException("Invalid TCP table size");
                for (int i=0;i<count;i++) {
                    var item=(OwnedRow)Marshal.PtrToStructure(IntPtr.Add(table,4+i*stride),typeof(OwnedRow));
                    var row=item.Row;
                    if (item.OwnerPid==(uint)pid && row.State==Established && row.LocalAddress==la &&
                        row.RemoteAddress==ra && (row.LocalPort&65535)==lp && (row.RemotePort&65535)==rp) {
                        match=row;return true;
                    }
                }
                return false;
            } finally { Marshal.FreeHGlobal(table); }
        }
        throw new InvalidOperationException("TCP table changed during lookup");
    }
    public static bool Owned(string local,int lport,string target,int rport,int pid) {
        TcpRow row;return Find(local,lport,target,rport,pid,out row);
    }
    public static int Release(string local,int lport,string target,int rport,int pid) {
        TcpRow row;
        if (!Find(local,lport,target,rport,pid,out row)) return -1;
        row.State=DeleteTcb;
        return (int)SetTcpEntry(ref row);
    }
}
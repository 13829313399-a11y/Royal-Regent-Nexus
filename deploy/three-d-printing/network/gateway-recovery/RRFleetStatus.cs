using System;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.RegularExpressions;

public static class RRFleetStatus {
    static bool Accept(X509Certificate cert, string pin) {
        if (cert == null) return false;
        using (var leaf = new X509Certificate2(cert))
        using (var sha = SHA256.Create()) {
            var hash = BitConverter.ToString(sha.ComputeHash(leaf.RawData)).Replace("-", "");
            var now = DateTime.UtcNow;
            return String.Equals(hash, pin, StringComparison.OrdinalIgnoreCase) && now >= leaf.NotBefore.ToUniversalTime() && now <= leaf.NotAfter.ToUniversalTime();
        }
    }

    static string ReadDocument(SslStream stream) {
        var header = new StringBuilder();
        while (header.Length < 2048) {
            int ch = stream.ReadByte();
            if (ch < 0) throw new InvalidDataException("incomplete_status_document");
            header.Append((char)ch);
            int n = header.Length;
            if (n >= 4 && header[n-4]=='\r' && header[n-3]=='\n' && header[n-2]=='\r' && header[n-1]=='\n') break;
        }
        string[] lines = header.ToString().Split(new string[] {"\r\n"},StringSplitOptions.None);
        if (header.Length >= 2048 || lines.Length < 3 || !lines[0].StartsWith("HTTP/") || !lines[0].Contains(" 200 ")) throw new InvalidDataException("cloud_evidence_unavailable");
        int size = 0;
        foreach (string line in lines) {
            if (line.StartsWith("Content-Length:",StringComparison.OrdinalIgnoreCase) && !Int32.TryParse(line.Substring(15).Trim(),out size))
                throw new InvalidDataException("invalid_status_document");
        }
        if (size < 1 || size > 8192) throw new InvalidDataException("invalid_status_document");
        var data = new byte[size];
        for (int offset=0; offset<size;) {
            int n=stream.Read(data,offset,size-offset);
            if (n==0) throw new InvalidDataException("incomplete_status_document");
            offset+=n;
        }
        return Encoding.UTF8.GetString(data);
    }

    public static string Read(string cloudIp, int port, string pin) {
        return Read(cloudIp,port,pin,"");
    }

    public static string Read(string cloudIp, int port, string pin, string check) {
        if (check.Length > 96 || !Regex.IsMatch(check, @"\A[a-zA-Z0-9_|-]*\z"))
            throw new InvalidDataException("invalid_guard_receipt");
        bool rejected = false;
        try {
            using (var tcp = new TcpClient(AddressFamily.InterNetwork)) {
                var ip=IPAddress.Parse(cloudIp);
                var connect=tcp.BeginConnect(ip,port,null,null);
                using (var wait=connect.AsyncWaitHandle) {
                    if (!wait.WaitOne(4000)) throw new IOException();
                    tcp.EndConnect(connect);
                }
                using (var tls=new SslStream(tcp.GetStream(),false,delegate(object sender,X509Certificate cert,X509Chain chain,SslPolicyErrors errors) {
                    rejected=!Accept(cert,pin);return !rejected;
                })) {
                    tls.ReadTimeout=4000;tls.WriteTimeout=4000;
                    var auth=tls.BeginAuthenticateAsClient(cloudIp,null,SslProtocols.Tls12,false,null,null);
                    using (var wait=auth.AsyncWaitHandle) {
                        if(!wait.WaitOne(5000)) throw new IOException();
                        tls.EndAuthenticateAsClient(auth);
                    }
                    var receipt=check.Length==0 ? "" : "X-RR-Guard: "+check+"\r\n";
                    var query=Encoding.ASCII.GetBytes("GET /v1/fleet HTTP/1.0\r\nHost: "+ip+"\r\n"+receipt+"Connection: close\r\n\r\n");
                    tls.Write(query,0,query.Length);
                    return ReadDocument(tls);
                }
            }
        } catch (InvalidDataException) { throw; }
        catch (Exception) {
            if (rejected) throw new InvalidDataException("status_certificate_rejected");
            throw new IOException("status_transport_unreachable");
        }
    }
}

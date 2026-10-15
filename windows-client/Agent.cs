using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.ServiceProcess;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;

public class AgentService : ServiceBase {
    public AgentService(){ ServiceName="SMAutomationAgent"; CanStop=true; AutoLog=false; }
    protected override void OnStart(string[] args){ Agent.Stop.Reset(); new Thread(Agent.Loop){IsBackground=true}.Start(); }
    protected override void OnStop(){ Agent.Stop.Set(); }
}

public static class Agent {
    public static string DirectoryPath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"SM Automation Agent");
    public static readonly ManualResetEvent Stop=new ManualResetEvent(false);
    static readonly JavaScriptSerializer Json=new JavaScriptSerializer(){MaxJsonLength=16*1024*1024,RecursionLimit=64};
    static Dictionary<string,object> State;
    static Dictionary<string,object> Config;
    static readonly Random Jitter=new Random();
    static DateTime LastCollection=DateTime.MinValue;
    const int Limit=8*1024*1024;
    public static Dictionary<string,object> Map(object value){return value as Dictionary<string,object> ?? new Dictionary<string,object>();}
    static string Text(Dictionary<string,object> map,string key){return map.ContainsKey(key)?Convert.ToString(map[key]):"";}
    static string Hex(byte[] data){return BitConverter.ToString(data).Replace("-","").ToLowerInvariant();}
    static string Hash(byte[] data){using(var h=SHA256.Create())return Hex(h.ComputeHash(data));}
    static void Atomic(string path,byte[] bytes){string temp=path+".pending";using(var f=new FileStream(temp,FileMode.Create,FileAccess.Write,FileShare.None)){f.Write(bytes,0,bytes.Length);f.Flush(true);}if(File.Exists(path))File.Replace(temp,path,null);else File.Move(temp,path);}
    static void Save(){byte[] plain=Encoding.UTF8.GetBytes(Json.Serialize(State));Atomic(Path.Combine(DirectoryPath,"identity.bin"),ProtectedData.Protect(plain,null,DataProtectionScope.LocalMachine));}
    static void Load(){
        Config=Map(Json.DeserializeObject(File.ReadAllText(Path.Combine(DirectoryPath,"connection.json"),Encoding.UTF8)));
        string path=Path.Combine(DirectoryPath,"identity.bin");
        if(File.Exists(path))State=Map(Json.DeserializeObject(Encoding.UTF8.GetString(ProtectedData.Unprotect(File.ReadAllBytes(path),null,DataProtectionScope.LocalMachine))));
        else {using(var key=new RSACryptoServiceProvider(2048)){key.PersistKeyInCsp=false;State=new Dictionary<string,object>{{"device_id",Guid.NewGuid().ToString("N")},{"private_key",key.ToXmlString(true)},{"history",new object[0]}};Save();}}
    }
    static RSACryptoServiceProvider Key(){var key=new RSACryptoServiceProvider();key.PersistKeyInCsp=false;key.FromXmlString(Text(State,"private_key"));return key;}
    static Dictionary<string,object> Public(){using(var key=Key()){var p=key.ExportParameters(false);return new Dictionary<string,object>{{"modulus",Convert.ToBase64String(p.Modulus)},{"exponent",Convert.ToBase64String(p.Exponent)}};}}
    static byte[] Exact(Stream stream,int size){byte[] bytes=new byte[size];int count=0;while(count<size){int n=stream.Read(bytes,count,size-count);if(n<=0)throw new IOException("Connection closed");count+=n;}return bytes;}
    static bool ValidateCertificate(object sender,X509Certificate cert,X509Chain chain,SslPolicyErrors errors){
        if(cert==null)return false;var current=new X509Certificate2(cert);
        if(DateTime.UtcNow<current.NotBefore.ToUniversalTime()||DateTime.UtcNow>current.NotAfter.ToUniversalTime())return false;
        string pin=Text(Config,"sha256");
        if(pin.Length==64)return String.Equals(Hash(current.RawData),pin,StringComparison.OrdinalIgnoreCase);
        return errors==SslPolicyErrors.None;
    }
    public static Dictionary<string,object> Call(string method,Dictionary<string,object> parameters){
        string host=Text(Config,"host");int port=Convert.ToInt32(Config["port"]);
        using(var socket=new TcpClient()){
            IAsyncResult pending=socket.BeginConnect(host,port,null,null);
            try{if(!pending.AsyncWaitHandle.WaitOne(15000))throw new System.TimeoutException("Server connection timeout");socket.EndConnect(pending);}finally{pending.AsyncWaitHandle.Close();}
            using(var tls=new SslStream(socket.GetStream(),false,ValidateCertificate)){
                tls.ReadTimeout=30000;tls.WriteTimeout=30000;
                tls.AuthenticateAsClient(host,null,System.Security.Authentication.SslProtocols.Tls12,Text(Config,"sha256").Length!=64);
                byte[] payload=Encoding.UTF8.GetBytes(Json.Serialize(new Dictionary<string,object>{{"method",method},{"params",parameters}}));
                if(payload.Length>16*1024*1024)throw new IOException("Request limit exceeded");
                byte[] header=BitConverter.GetBytes(IPAddress.HostToNetworkOrder(payload.Length));tls.Write(header,0,4);tls.Write(payload,0,payload.Length);tls.Flush();
                byte[] length=Exact(tls,4);int size=IPAddress.NetworkToHostOrder(BitConverter.ToInt32(length,0));
                if(size<=0||size>16*1024*1024)throw new IOException("Invalid response frame");
                var response=Map(Json.DeserializeObject(Encoding.UTF8.GetString(Exact(tls,size))));
                if(!response.ContainsKey("ok")||!Convert.ToBoolean(response["ok"]))throw new IOException("Server rejected device request");
                return Map(response["result"]);
            }
        }
    }
    static Dictionary<string,object> Exchange(Dictionary<string,object> payload){
        var hello=Call("agent.hello",new Dictionary<string,object>{{"device_id",State["device_id"]},{"public_key",Public()}});
        string body=Json.Serialize(payload);
        string text="SM-AUTOMATION-AGENT-v1\n"+Text(hello,"challenge_id")+"\n"+Text(hello,"nonce")+"\n"+body;
        byte[] signature;using(var key=Key())signature=key.SignData(Encoding.UTF8.GetBytes(text),CryptoConfig.MapNameToOID("SHA256"));
        return Call("agent.exchange",new Dictionary<string,object>{{"challenge_id",hello["challenge_id"]},{"payload",body},{"signature",Convert.ToBase64String(signature)}});
    }
    static void Status(string value){
        Atomic(Path.Combine(DirectoryPath,"status.json"),Encoding.UTF8.GetBytes(Json.Serialize(new Dictionary<string,object>{{"status",value},{"time",DateTime.UtcNow.ToString("o")}})));
    }
    static void Log(string value){try{string path=Path.Combine(DirectoryPath,"agent.log");if(File.Exists(path)&&new FileInfo(path).Length>1024*1024)File.Delete(path);File.AppendAllText(path,DateTime.UtcNow.ToString("o")+" "+value+Environment.NewLine,Encoding.UTF8);}catch{}}
    static string Script(){using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("ci-script"))using(var reader=new StreamReader(stream,Encoding.UTF8))return reader.ReadToEnd();}
    static Dictionary<string,object> RunPowerShell(string script,int seconds){
        // Every helper is hidden; output is bounded and a job object kills descendants.
        string encoded=Convert.ToBase64String(Encoding.Unicode.GetBytes("$OutputEncoding=[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding $false;\n"+script));
        var start=new ProcessStartInfo(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"WindowsPowerShell\\v1.0\\powershell.exe"),"-NoLogo -NoProfile -NonInteractive -EncodedCommand "+encoded);
        start.UseShellExecute=false;start.CreateNoWindow=true;start.RedirectStandardOutput=true;start.RedirectStandardError=true;start.StandardOutputEncoding=Encoding.UTF8;start.StandardErrorEncoding=Encoding.UTF8;
        var output=new StringBuilder();var errors=new StringBuilder();bool overflow=false;
        using(var process=new Process())using(var job=new ProcessTree()){
            process.StartInfo=start;
            process.OutputDataReceived+=(s,e)=>{if(e.Data!=null)lock(output){if(output.Length+e.Data.Length<1024*1024)output.AppendLine(e.Data);else overflow=true;}};
            process.ErrorDataReceived+=(s,e)=>{if(e.Data!=null)lock(errors){if(errors.Length+e.Data.Length<65536)errors.AppendLine(e.Data);else overflow=true;}};
            process.Start();job.Attach(process);process.BeginOutputReadLine();process.BeginErrorReadLine();
            DateTime deadline=DateTime.UtcNow.AddSeconds(seconds);
            while(!process.WaitForExit(200)){if(Stop.WaitOne(0)||DateTime.UtcNow>deadline||overflow){job.Close();try{process.Kill();}catch{}throw new IOException("Execution stopped: timeout, cancellation or output limit; completion may be unknown");}}
            process.WaitForExit();if(overflow)throw new IOException("Output limit exceeded");
            return new Dictionary<string,object>{{"stdout",output.ToString()},{"stderr",errors.ToString()},{"exit_code",process.ExitCode}};
        }
    }
    static Dictionary<string,object> Collect(){var result=RunPowerShell(Script(),90);if(Convert.ToInt32(result["exit_code"])!=0)throw new IOException("CI discovery failed");return Map(Json.DeserializeObject(Text(result,"stdout")));}
    static void RegularPath(string path,bool mustExist){
        if(String.IsNullOrWhiteSpace(path)||!Path.IsPathRooted(path)||path.StartsWith("\\\\")||path.IndexOf(':',2)>=0)throw new IOException("Use an absolute local drive path");
        string current=Path.GetFullPath(path);
        while(!String.IsNullOrEmpty(current)){
            if(File.Exists(current)||Directory.Exists(current)){if((File.GetAttributes(current)&FileAttributes.ReparsePoint)!=0)throw new IOException("Links and reparse points are not allowed");}
            else if(mustExist)throw new FileNotFoundException();
            current=Path.GetDirectoryName(current);
        }
    }
    static Dictionary<string,object> Transfer(Dictionary<string,object> options){
        string path=Text(options,"client_path");bool upload=Text(options,"direction")=="upload";RegularPath(path,upload);
        if(upload){
            using(var source=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read)){
                if(source.Length>Limit)throw new IOException("CLIENT file limit is 8 MiB");byte[] bytes=Exact(source,Convert.ToInt32(source.Length));
                return new Dictionary<string,object>{{"content",Convert.ToBase64String(bytes)},{"sha256",Hash(bytes)},{"bytes",bytes.Length}};
            }
        }
        byte[] content=Convert.FromBase64String(Text(options,"content"));if(content.Length>Limit||Hash(content)!=Text(options,"sha256"))throw new IOException("File checksum mismatch");
        if(File.Exists(path)||Directory.Exists(path))throw new IOException("Destination already exists");
        string parent=Path.GetDirectoryName(Path.GetFullPath(path));if(!Directory.Exists(parent))throw new IOException("Destination directory does not exist");
        string temp=Path.Combine(parent,".sm-agent-"+Guid.NewGuid().ToString("N"));
        try{using(var f=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){f.Write(content,0,content.Length);f.Flush(true);}File.Move(temp,path);}finally{if(File.Exists(temp))File.Delete(temp);}
        return new Dictionary<string,object>{{"sha256",Hash(content)},{"bytes",content.Length},{"client_path",path}};
    }
    static Dictionary<string,object> Execute(Dictionary<string,object> task){
        string kind=Text(task,"kind");var options=Map(task.ContainsKey("options")?task["options"]:null);
        if(kind=="ci_inventory")return Collect();
        if(kind=="connections"){var value=RunPowerShell("netstat -ano; exit $LASTEXITCODE",30);if(Convert.ToInt32(value["exit_code"])!=0)throw new IOException("Connection discovery failed");return value;}
        if(kind=="command")return RunPowerShell(Text(options,"command"),90);
        if(kind=="transfer")return Transfer(options);
        throw new IOException("Unsupported agent operation");
    }
    static void Task(Dictionary<string,object> task){
        string id=Text(task,"id");if(!System.Text.RegularExpressions.Regex.IsMatch(id,"^[a-f0-9]{32}$"))throw new IOException("Invalid task identity");
        var history=new List<object>((object[])State["history"]);
        if(history.Contains(id)){State["outbox"]=new Dictionary<string,object>{{"id",id},{"status","failed"},{"error","Task already acknowledged; it will not be repeated"}};Save();return;}
        // Persist intent before execution. After a crash, never repeat a possibly mutating operation.
        State["started_task"]=id;Save();
        Dictionary<string,object> result;
        try {var data=Execute(task);bool ok=!data.ContainsKey("exit_code")||Convert.ToInt32(data["exit_code"])==0;result=new Dictionary<string,object>{{"id",id},{"status",ok?"completed":"failed"},{"result",data}};}
        catch(Exception e){result=new Dictionary<string,object>{{"id",id},{"status","failed"},{"error",e.Message}};}
        State["outbox"]=result;State.Remove("started_task");Save();
    }
    public static void Loop(){
        int failures=0;
        try{Load();}catch(Exception e){Log("Startup failed: "+e.GetType().Name);return;}
        if(State.ContainsKey("started_task")&&!State.ContainsKey("outbox")){State["outbox"]=new Dictionary<string,object>{{"id",State["started_task"]},{"status","failed"},{"error","Agent restarted during execution; completion is unknown and the task was not repeated"}};State.Remove("started_task");Save();}
        while(!Stop.WaitOne(0)){
            try{
                var payload=new Dictionary<string,object>{{"device_id",State["device_id"]},{"hostname",Environment.MachineName},{"version","1.0.0"}};
                if(DateTime.UtcNow-LastCollection>TimeSpan.FromMinutes(15)){try{payload["observation"]=Collect();}catch{payload["collection_error"]="Windows CI discovery failed";}}
                if(State.ContainsKey("outbox"))payload["results"]=new object[]{State["outbox"]};
                var response=Exchange(payload);
                if(payload.ContainsKey("observation")||payload.ContainsKey("collection_error"))LastCollection=DateTime.UtcNow;
                if(response.ContainsKey("ack"))foreach(object item in (object[])response["ack"]){
                    if(State.ContainsKey("outbox")&&Text(Map(State["outbox"]),"id")==Convert.ToString(item)){
                        var history=new List<object>((object[])State["history"]);history.Add(item);while(history.Count>128)history.RemoveAt(0);State["history"]=history.ToArray();State.Remove("outbox");Save();
                    }
                }
                Status("connected");failures=0;
                var task=Map(response.ContainsKey("task")?response["task"]:null);
                if(task.Count>0){Task(task);continue;}
                Stop.WaitOne(30000+Jitter.Next(0,5000));
            }catch(Exception e){Log("Connection/operation failed: "+e.GetType().Name);Status("retrying");failures++;Stop.WaitOne(Math.Min(300000,5000*(1<<Math.Min(failures,5)))+Jitter.Next(0,3000));}
        }
    }
    static int SelfTest(){
        var unicode=new Dictionary<string,object>{{"name","SM test"},{"value",123}};
        if(Text(Map(Json.DeserializeObject(Json.Serialize(unicode))),"name")!="SM test")throw new Exception("JSON");
        using(var key=new RSACryptoServiceProvider(2048)){key.PersistKeyInCsp=false;byte[] b=Encoding.UTF8.GetBytes("SM-AUTOMATION-AGENT-v1");byte[] sig=key.SignData(b,CryptoConfig.MapNameToOID("SHA256"));if(!key.VerifyData(b,CryptoConfig.MapNameToOID("SHA256"),sig))throw new Exception("RSA");}
        if(Script().IndexOf("cpu_topology")<0)throw new Exception("CI resource");
        Console.WriteLine("PASS: Windows agent crypto/JSON/resource self-test (no service or machine discovery)");return 0;
    }
    static int ProtocolFixture(string[] args){
        DirectoryPath=Path.GetFullPath(args[1]);Load();
        string mode=args.Length>2?args[2]:"enroll";
        var payload=new Dictionary<string,object>{{"device_id",State["device_id"]},{"hostname","windows-protocol-fixture"},{"version","protocol-fixture"}};
        if(mode=="uninstall")payload["uninstall"]=true;
        else payload["observation"]=new Dictionary<string,object>{{"actual_hostname","windows-protocol-fixture"},{"primary_ip","127.0.0.1"},{"os_name","Windows fixture"},{"cpu_topology",new object[]{new Dictionary<string,object>{{"cores",2},{"logical",4}}}}};
        if(State.ContainsKey("outbox"))payload["results"]=new object[]{State["outbox"]};
        var reply=Exchange(payload);
        var task=Map(reply.ContainsKey("task")?reply["task"]:null);
        if(mode=="task"&&task.Count>0){
            if(Text(task,"kind")!="command"||Text(Map(task["options"]),"command")!="Write-Output 'SM-agent-fixture'")throw new IOException("Only the fixed harmless protocol fixture command is allowed");
            Task(task);reply=Exchange(new Dictionary<string,object>{{"device_id",State["device_id"]},{"hostname","windows-protocol-fixture"},{"results",new object[]{State["outbox"]}}});
        }
        Console.WriteLine(Json.Serialize(reply));return 0;
    }
    public static int Main(string[] args){
        try{
            if(args.Length>1&&args[0]=="--protocol-test")return ProtocolFixture(args);
            if(args.Length>0&&args[0]=="--self-test")return SelfTest();
            if(args.Length>0&&args[0]=="--notify-uninstall"){Load();Exchange(new Dictionary<string,object>{{"device_id",State["device_id"]},{"hostname",Environment.MachineName},{"version","1.0.0"},{"uninstall",true}});return 0;}
            if(args.Length>0&&args[0]=="--console"){Loop();return 0;}
            ServiceBase.Run(new AgentService());return 0;
        }catch(Exception e){Log("Stopped: "+e.GetType().Name);return 1;}
    }
}

public sealed class ProcessTree : IDisposable {
    IntPtr handle;
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]struct Basic {public long processTime,jobTime;public uint flags;public UIntPtr min,max;public uint active;public UIntPtr affinity;public uint priority,scheduling;}
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]struct IO {public ulong a,b,c,d,e,f;}
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]struct Extended {public Basic basic;public IO io;public UIntPtr processMemory,jobMemory,peakProcess,peakJob;}
    [System.Runtime.InteropServices.DllImport("kernel32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode)]static extern IntPtr CreateJobObject(IntPtr attrs,string name);
    [System.Runtime.InteropServices.DllImport("kernel32.dll")]static extern bool SetInformationJobObject(IntPtr job,int cls,IntPtr info,uint size);
    [System.Runtime.InteropServices.DllImport("kernel32.dll")]static extern bool AssignProcessToJobObject(IntPtr job,IntPtr process);
    [System.Runtime.InteropServices.DllImport("kernel32.dll")]static extern bool CloseHandle(IntPtr handle);
    public ProcessTree(){handle=CreateJobObject(IntPtr.Zero,null);var limits=new Extended();limits.basic.flags=0x2000;int size=System.Runtime.InteropServices.Marshal.SizeOf(limits);IntPtr p=System.Runtime.InteropServices.Marshal.AllocHGlobal(size);try{System.Runtime.InteropServices.Marshal.StructureToPtr(limits,p,false);if(handle==IntPtr.Zero||!SetInformationJobObject(handle,9,p,(uint)size))throw new IOException("Cannot restrict helper process");}finally{System.Runtime.InteropServices.Marshal.FreeHGlobal(p);}}
    public void Attach(Process process){if(!AssignProcessToJobObject(handle,process.Handle)){try{process.Kill();}catch{}throw new IOException("Cannot bind helper process");}}
    public void Close(){if(handle!=IntPtr.Zero){CloseHandle(handle);handle=IntPtr.Zero;}}
    public void Dispose(){Close();}
}

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Reflection;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Win32;

public class Setup : Form {
    static bool Preview=false;
    protected override bool ShowWithoutActivation { get { return Preview; } }
    readonly TextBox host=new TextBox(){Width=280};
    readonly NumericUpDown port=new NumericUpDown(){Minimum=1,Maximum=65535,Value=7443,Width=100};
    readonly Label status=new Label(){AutoSize=false,Width=470,Height=95};
    readonly Button install=new Button(){Text="설치 및 연결",Width=140,Height=38};
    readonly Button uninstall=new Button(){Text="클라이언트 제거",Width=140,Height=38};
    static readonly string DirectoryPath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"SM Automation Agent");
    static readonly string InstallPath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),"SM Automation Agent");
    static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
    public Setup(){
        Text="SM Automation Windows CLIENT 설치";ClientSize=new Size(520,320);FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;StartPosition=FormStartPosition.CenterScreen;BackColor=Color.FromArgb(243,246,251);ForeColor=Color.FromArgb(35,52,76);Font=new Font("Malgun Gothic",10);
        var title=new Label(){Text="Linux SERVER 연결",AutoSize=true,Font=new Font(Font,FontStyle.Bold),Location=new Point(24,20)};Controls.Add(title);
        var ipLabel=new Label(){Text="SERVER IP / DNS",AutoSize=true,Location=new Point(24,68)};Controls.Add(ipLabel);host.Location=new Point(205,64);Controls.Add(host);
        var portLabel=new Label(){Text="통신 포트 (TLS)",AutoSize=true,Location=new Point(24,113)};Controls.Add(portLabel);port.Location=new Point(205,108);Controls.Add(port);
        install.Location=new Point(205,155);uninstall.Location=new Point(355,155);Controls.Add(install);Controls.Add(uninstall);status.Location=new Point(24,210);status.Text="IP와 포트만 입력하면 LocalSystem 서비스가 자동 시작되고 장비가 등록됩니다. SERVER 관리자가 명령을 실행할 수 있습니다. CLIENT 인바운드 포트/SSH는 설정하지 않습니다.";Controls.Add(status);
        install.Click+=async(s,e)=>{if(String.IsNullOrWhiteSpace(host.Text)||Uri.CheckHostName(host.Text.Trim())==UriHostNameType.Unknown){status.Text="올바른 SERVER IP 또는 DNS를 입력하세요.";return;}string address=host.Text.Trim();int number=(int)port.Value;install.Enabled=uninstall.Enabled=false;status.Text="서비스 설치 및 SERVER 등록 중...";try{string message=await Task.Run(()=>Install(address,number));status.Text=message;}catch(Exception error){status.Text="설치 실패: "+error.Message;}finally{install.Enabled=uninstall.Enabled=true;}};
        uninstall.Click+=async(s,e)=>{if(MessageBox.Show(this,"이 Windows CLIENT 서비스를 제거하시겠습니까? SERVER에는 제거 상태를 통보합니다.","CLIENT 제거",MessageBoxButtons.YesNo)!=DialogResult.Yes)return;install.Enabled=uninstall.Enabled=false;try{status.Text=await Task.Run(()=>Uninstall());}catch(Exception error){status.Text="제거 실패: "+error.Message;}finally{install.Enabled=uninstall.Enabled=true;}};
    }
    static int Run(string file,string args,bool acceptFailure){
        if(file=="sc.exe")file=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System),"sc.exe");
        using(var process=new Process()){process.StartInfo=new ProcessStartInfo(file,args){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true};process.Start();var stdout=process.StandardOutput.ReadToEndAsync();var stderr=process.StandardError.ReadToEndAsync();if(!process.WaitForExit(45000)){try{process.Kill();}catch{}throw new IOException("서비스 작업 시간 초과");}Task.WaitAll(stdout,stderr);if(process.ExitCode!=0&&!acceptFailure)throw new IOException("Windows 서비스 설정에 실패했습니다 (코드 "+process.ExitCode+")");return process.ExitCode;}
    }
    static void Restrict(string path){
        if((File.GetAttributes(path)&FileAttributes.ReparsePoint)!=0)throw new IOException("설치 경로는 링크일 수 없습니다.");
        var security=new DirectorySecurity();security.SetOwner(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid,null));security.SetAccessRuleProtection(true,false);
        foreach(var sid in new[]{WellKnownSidType.LocalSystemSid,WellKnownSidType.BuiltinAdministratorsSid})security.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(sid,null),FileSystemRights.FullControl,InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit,PropagationFlags.None,AccessControlType.Allow));
        if(String.Equals(Path.GetFullPath(path),Path.GetFullPath(InstallPath),StringComparison.OrdinalIgnoreCase))security.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid,null),FileSystemRights.ReadAndExecute,InheritanceFlags.ContainerInherit|InheritanceFlags.ObjectInherit,PropagationFlags.None,AccessControlType.Allow));
        new DirectoryInfo(path).SetAccessControl(security);
    }
    [System.Runtime.InteropServices.DllImport("kernel32.dll",CharSet=System.Runtime.InteropServices.CharSet.Unicode,SetLastError=true)]
    static extern bool MoveFileEx(string source,string target,int flags);
    const string UninstallKey="SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SMAutomationAgent";
    static string Pin(){
        // A GUI-generated installer appends a PUBLIC certificate fingerprint, never a password.
        byte[] bytes=File.ReadAllBytes(Assembly.GetExecutingAssembly().Location);string tail=Encoding.UTF8.GetString(bytes,Math.Max(0,bytes.Length-4096),Math.Min(4096,bytes.Length));string marker="\nSM_AUTOMATION_SERVER_PIN_V1\n";int i=tail.LastIndexOf(marker,StringComparison.Ordinal);if(i<0)return "";
        var metadata=Json.Deserialize<Dictionary<string,string>>(tail.Substring(i+marker.Length));string pin=metadata["sha256"];
        if(!System.Text.RegularExpressions.Regex.IsMatch(pin,"^[a-f0-9]{64}$"))throw new IOException("설치 파일의 SERVER 인증 정보가 잘못되었습니다.");return pin;
    }
    static void StopService(){
        Run("sc.exe","stop SMAutomationAgent",true);
        using(var service=new System.ServiceProcess.ServiceController("SMAutomationAgent")){try{service.WaitForStatus(System.ServiceProcess.ServiceControllerStatus.Stopped,TimeSpan.FromSeconds(20));}catch(InvalidOperationException){} }
    }
    static string Install(string host,int port){
        StopService();
        Directory.CreateDirectory(DirectoryPath);Restrict(DirectoryPath);Directory.CreateDirectory(InstallPath);Restrict(InstallPath);
        // Never reuse an untrusted pre-created identity or a link in product state.
        foreach(string file in Directory.GetFiles(DirectoryPath)){
            if((File.GetAttributes(file)&FileAttributes.ReparsePoint)!=0)throw new IOException("상태 파일은 링크일 수 없습니다.");
            if(Path.GetFileName(file)=="identity.bin"){
                var owner=(SecurityIdentifier)File.GetAccessControl(file).GetOwner(typeof(SecurityIdentifier));
                if(!owner.IsWellKnown(WellKnownSidType.LocalSystemSid)&&!owner.IsWellKnown(WellKnownSidType.BuiltinAdministratorsSid))File.Delete(file);
                else {var security=new FileSecurity();security.SetAccessRuleProtection(true,false);security.SetOwner(new SecurityIdentifier(WellKnownSidType.BuiltinAdministratorsSid,null));foreach(var sid in new[]{WellKnownSidType.LocalSystemSid,WellKnownSidType.BuiltinAdministratorsSid})security.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(sid,null),FileSystemRights.FullControl,AccessControlType.Allow));File.SetAccessControl(file,security);}
            }else if(Path.GetFileName(file).EndsWith(".pending")||Path.GetFileName(file)=="agent.log")File.Delete(file);
        }
        string exe=Path.Combine(InstallPath,"SM.Agent.exe");
        if(File.Exists(exe))File.Delete(exe);
        using(var stream=Assembly.GetExecutingAssembly().GetManifestResourceStream("agent-exe"))using(var file=new FileStream(exe,FileMode.Create,FileAccess.Write,FileShare.None)){stream.CopyTo(file);file.Flush(true);}
        var connection=new Dictionary<string,object>{{"host",host},{"port",port},{"sha256",Pin()}};
        string config=Path.Combine(DirectoryPath,"connection.json");if(File.Exists(config))File.Delete(config);
        using(var stream=new FileStream(config,FileMode.CreateNew,FileAccess.Write,FileShare.None))using(var writer=new StreamWriter(stream,new UTF8Encoding(false)))writer.Write(Json.Serialize(connection));
        string status=Path.Combine(DirectoryPath,"status.json");if(File.Exists(status))File.Delete(status);
        string bin="\\\""+exe+"\\\"";
        int exists=Run("sc.exe","query SMAutomationAgent",true);
        if(exists!=0)Run("sc.exe","create SMAutomationAgent binPath= \""+bin+"\" start= delayed-auto obj= LocalSystem DisplayName= \"SM Automation Windows Agent\"",false);
        else Run("sc.exe","config SMAutomationAgent binPath= \""+bin+"\" start= delayed-auto obj= LocalSystem",false);
        Run("sc.exe","description SMAutomationAgent \"Outbound TLS management connection to SM Automation Linux SERVER\"",true);
        Run("sc.exe","failure SMAutomationAgent reset= 86400 actions= restart/10000/restart/30000/restart/60000",true);
        string uninstaller=Path.Combine(InstallPath,"Uninstall.exe");
        if(!String.Equals(Path.GetFullPath(Assembly.GetExecutingAssembly().Location),Path.GetFullPath(uninstaller),StringComparison.OrdinalIgnoreCase))File.Copy(Assembly.GetExecutingAssembly().Location,uninstaller,true);
        using(var entry=Registry.LocalMachine.CreateSubKey(UninstallKey)){
            entry.SetValue("DisplayName","SM Automation Windows Agent");entry.SetValue("DisplayVersion","1.0.0");entry.SetValue("Publisher","SM Automation");entry.SetValue("InstallLocation",InstallPath);
            entry.SetValue("UninstallString","\""+uninstaller+"\" --uninstall");entry.SetValue("NoModify",1);entry.SetValue("NoRepair",1);
        }
        Run("sc.exe","start SMAutomationAgent",false);
        DateTime deadline=DateTime.UtcNow.AddSeconds(65);
        while(DateTime.UtcNow<deadline){try{if(File.Exists(status)&&File.ReadAllText(status).Contains("connected"))return "설치 및 SERVER 자동 등록 완료. GUI 장비 목록과 CI 화면에서 확인하세요.";}catch(IOException){}System.Threading.Thread.Sleep(1000);}
        return "설치는 완료되었으며 SERVER 연결을 재시도 중입니다. SERVER IP/포트·등록 허용 기간·네트워크 범위·인증서를 확인하세요.";
    }
    static string Uninstall(){
        string exe=Path.Combine(InstallPath,"SM.Agent.exe");bool notified=File.Exists(exe)&&Run(exe,"--notify-uninstall",true)==0;
        Run("sc.exe","delete SMAutomationAgent",true);
        // Only exact, product-owned directories may be removed.
        foreach(string path in new[]{InstallPath,DirectoryPath}){
            string expected=Path.GetFullPath(path);
            if(!String.Equals(Path.GetFileName(expected),"SM Automation Agent",StringComparison.Ordinal))throw new IOException("Invalid removal target");
            if(Directory.Exists(expected)){if((File.GetAttributes(expected)&FileAttributes.ReparsePoint)!=0)throw new IOException("Removal target cannot be a link");
                string own=Path.GetFullPath(Assembly.GetExecutingAssembly().Location);
                if(own.StartsWith(expected+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)){
                    foreach(string file in Directory.GetFiles(expected)){
                        if(String.Equals(Path.GetFullPath(file),own,StringComparison.OrdinalIgnoreCase)){
                            if(!MoveFileEx(file,null,4))throw new IOException("실행 중인 제거 파일의 정리를 예약할 수 없습니다.");
                        }else File.Delete(file);
                    }
                    if(!MoveFileEx(expected,null,4))throw new IOException("설치 폴더 정리를 예약할 수 없습니다.");
                }else Directory.Delete(expected,true);}
        }
        Registry.LocalMachine.DeleteSubKeyTree(UninstallKey,false);
        return notified?"클라이언트를 제거하고 SERVER에 제거 상태를 통보했습니다. SERVER 목록의 제거는 관리자가 수행할 수 있습니다.":"클라이언트를 제거했습니다. SERVER에 연결할 수 없어 제거 통보는 전달되지 않았으며, SERVER에는 오프라인으로 표시됩니다.";
    }
    [STAThread]public static int Main(string[] args){
        Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
        if(args.Length>1&&args[0]=="--render-preview"){
            Preview=true;
            using(var form=new Setup())using(var bitmap=new Bitmap(form.Width,form.Height)){
                form.host.Text="192.0.2.10";form.install.Enabled=false;form.uninstall.Enabled=false;
                form.ShowInTaskbar=false;form.StartPosition=FormStartPosition.Manual;form.Location=new Point(-32000,-32000);form.Show();Application.DoEvents();form.DrawToBitmap(bitmap,new Rectangle(0,0,bitmap.Width,bitmap.Height));bitmap.Save(args[1],System.Drawing.Imaging.ImageFormat.Png);
            }return 0;
        }
        if(args.Length>0&&args[0]=="--uninstall"){try{MessageBox.Show(Uninstall(),"SM Automation CLIENT 제거");return 0;}catch(Exception error){MessageBox.Show(error.Message,"제거 실패");return 1;}}
        if(args.Length>0&&args[0]=="--self-test"){if(Pin().Length!=0&&Pin().Length!=64)throw new Exception("pin");return 0;}
        Application.Run(new Setup());return 0;
    }
}

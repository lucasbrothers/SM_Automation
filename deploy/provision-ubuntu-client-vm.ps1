$ErrorActionPreference='Stop'
Import-Module Hyper-V
New-Item -ItemType Directory -Path 'D:\WSL\VM-Setup' -Force | Out-Null
$root='D:\WSL\VM-Setup'
try {
 $name='Ubuntu-Client';$switchName='SM-Test-Private';$prefix='192.168.250.0/24';$gateway='192.168.250.1'
 $disk='D:\WSL\Ubuntu-Client-VM\Ubuntu-Client-30G.vhdx';$seed='D:\WSL\VM-Setup\seed\seed.iso'
 if (-not (Test-Path -LiteralPath $disk) -or -not (Test-Path -LiteralPath $seed)) { throw 'VM disk or seed ISO missing' }
 $existing=Get-VM -Name $name -ErrorAction SilentlyContinue
 if ($existing -and $existing.Path -notlike 'D:\WSL\Ubuntu-Client-VM*') { throw 'A different VM already uses this name' }
 $switch=Get-VMSwitch -Name $switchName -ErrorAction SilentlyContinue
 if (-not $switch) {
  if (Get-NetIPAddress -AddressFamily IPv4 | Where-Object IPAddress -like '192.168.250.*') { throw 'Planned subnet is already in use' }
  $switch=New-VMSwitch -Name $switchName -SwitchType Internal
 }
 $adapter=Get-NetAdapter -Name ('vEthernet ('+$switchName+')')
 if (-not (Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object IPAddress -eq $gateway)) {
  New-NetIPAddress -InterfaceIndex $adapter.ifIndex -IPAddress $gateway -PrefixLength 24 | Out-Null
 }
 Set-NetIPInterface -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -Forwarding Enabled
 Get-NetIPInterface -AddressFamily IPv4 | Where-Object InterfaceAlias -like 'vEthernet (WSL*' | Set-NetIPInterface -Forwarding Enabled
 try {
  if (-not (Get-NetNat -Name 'SM-Test-NAT' -ErrorAction SilentlyContinue)) { New-NetNat -Name 'SM-Test-NAT' -InternalIPInterfaceAddressPrefix $prefix | Out-Null }
 } catch { $_.Exception.Message | Set-Content -LiteralPath ($root+'\nat-warning.txt') -Encoding utf8 }
 if (-not (Get-NetFirewallRule -Name 'SM-Lab-SSH-From-WSL' -ErrorAction SilentlyContinue)) {
  New-NetFirewallRule -Name 'SM-Lab-SSH-From-WSL' -DisplayName 'SM lab SSH from local WSL only' -Direction Inbound -Protocol TCP -LocalPort 22 -RemoteAddress '172.22.192.0/20' -Action Allow -Profile Any | Out-Null
 }
 if (-not $existing) {
  $vm=New-VM -Name $name -Generation 2 -MemoryStartupBytes 2GB -VHDPath $disk -Path 'D:\WSL\Ubuntu-Client-VM' -SwitchName $switchName
  Set-VMProcessor -VMName $name -Count 2
  Set-VMMemory -VMName $name -DynamicMemoryEnabled $true -MinimumBytes 1GB -StartupBytes 2GB -MaximumBytes 3GB
  Set-VMNetworkAdapter -VMName $name -StaticMacAddress '00155D250002'
  Add-VMDvdDrive -VMName $name -Path $seed
  Set-VMFirmware -VMName $name -EnableSecureBoot On -SecureBootTemplate MicrosoftUEFICertificateAuthority -FirstBootDevice (Get-VMHardDiskDrive -VMName $name)
  Set-VM -Name $name -AutomaticCheckpointsEnabled $false -AutomaticStartAction StartIfRunning -AutomaticStopAction ShutDown
 }
 if ((Get-VM -Name $name).State -ne 'Running') { Start-VM -Name $name | Out-Null }
 Get-VM -Name $name | Select-Object Name,State,Id,Generation,MemoryAssigned,ProcessorCount,Path | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ($root+'\vm-result.json') -Encoding utf8
 Get-VMNetworkAdapter -VMName $name | Select-Object SwitchName,MacAddress,IPAddresses | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath ($root+'\vm-network.json') -Encoding utf8
} catch {
 $_.Exception.Message | Set-Content -LiteralPath ($root+'\vm-error.txt') -Encoding utf8
 exit 1
}



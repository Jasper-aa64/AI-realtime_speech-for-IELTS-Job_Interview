# Remove IELTS Windows services. Run in elevated PowerShell.
#Requires -RunAsAdministrator

$NssmExe = "C:\Users\liangjunming\tools\nssm-2.24\win64\nssm.exe"
foreach ($svc in @("ielts-django", "ielts-worker")) {
    Write-Host "Removing $svc ..."
    Stop-Service $svc -Force -ErrorAction SilentlyContinue
    & $NssmExe remove $svc confirm
}
Write-Host "Done."

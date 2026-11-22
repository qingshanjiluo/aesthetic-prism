$repo = 'G:\皮皮\编程项目\aesthetic-prism'
$py = 'C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe'
$log = Join-Path $repo 'reports\resume_kd_run2.log'
$err = Join-Path $repo 'reports\resume_kd_run2.err.log'

$names = @('NO_PROXY','HTTPS_PROXY','HTTP_PROXY','ALL_PROXY')
foreach ($n in $names) {
  Remove-Item -Path ("Env:" + $n) -ErrorAction SilentlyContinue
  Remove-Item -Path ("Env:" + $n.ToLower()) -ErrorAction SilentlyContinue
}

$args = @('-X','utf8',(Join-Path $repo 'scripts\resume_kd.py'))
$p = Start-Process -FilePath $py -ArgumentList $args -WorkingDirectory $repo -RedirectStandardOutput $log -RedirectStandardError $err -WindowStyle Hidden -PassThru
Write-Output ("started PID=" + $p.Id)
Start-Sleep -Seconds 90
Write-Output ("alive=" + (-not $p.HasExited))
if (Test-Path $log) { Get-Content $log -Tail 5 }
if (Test-Path $err) { Get-Content $err -Tail 5 }

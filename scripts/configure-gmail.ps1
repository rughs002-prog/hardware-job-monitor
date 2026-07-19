$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $ProjectDirectory ".env"

Write-Host "Paste the 16-character Gmail App Password. It will not be displayed."
$SecurePassword = Read-Host -AsSecureString
$Pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecurePassword)
try {
    $AppPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Pointer).Replace(" ", "")
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Pointer)
}

if ($AppPassword.Length -lt 16) {
    throw "The App Password appears too short. No file was changed."
}

$Content = Get-Content -Raw -LiteralPath $EnvFile
$Content = [regex]::Replace($Content, '(?m)^SMTP_PASSWORD=.*$', "SMTP_PASSWORD=$AppPassword")
Set-Content -LiteralPath $EnvFile -Value $Content -Encoding utf8
Write-Host "Gmail settings saved locally in the Git-ignored .env file."

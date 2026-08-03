$ErrorActionPreference = "Stop"

$packageRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $packageRoot

$checkpoint = Join-Path $packageRoot "training_runs\protected-v4-seed137\best.pth"
$detector = Join-Path $packageRoot "yolo26n-pose.pt"

if (-not (Test-Path -LiteralPath $checkpoint)) {
    throw "未找到异常行为分类模型：$checkpoint"
}

if (-not (Test-Path -LiteralPath $detector)) {
    throw "未找到人员检测模型：$detector"
}

$env:ANOMALY_CLASSIFIER_CHECKPOINT = (Resolve-Path -LiteralPath $checkpoint).Path

Write-Host "正在启动异常行为识别 API..."
Write-Host "本机地址：http://127.0.0.1:8000"
Write-Host "局域网地址：http://<本机IPv4地址>:8000"

python -m anomaly_tracker --host 0.0.0.0 --port 8000

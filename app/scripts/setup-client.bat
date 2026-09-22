@echo off
chcp 65001 >nul
setlocal

:: ===================================================================
:: Chienami HTTPS初期設定スクリプト（研究室メンバー向け, Issue #26）
::
:: 以下の2つを1回の実行でまとめて行う。
::   1. hostsファイルへ knowledge.lab.local / auth.lab.local / search.lab.local を追記（名前解決）
::   2. Chienamiのルート証明書(chienami-root-ca.crt)をこのPCへ信頼登録
::
:: 実行前の準備:
::   - このファイルと同じフォルダに chienami-root-ca.crt を置くこと
::   - 下の HOST_IP を、Reverse Proxyを動かしているホストPCのLAN内IPアドレスに
::     書き換えてから配布すること
::   - 実行時は「管理者として実行」を選ぶこと（hosts書き込み・証明書登録に必要）
:: ===================================================================

set HOST_IP=192.0.2.1
set CERT_FILE=%~dp0chienami-root-ca.crt
set HOSTS_FILE=%WINDIR%\System32\drivers\etc\hosts

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [エラー] 管理者として実行してください（このファイルを右クリック→「管理者として実行」）。
    pause
    exit /b 1
)

if not exist "%CERT_FILE%" (
    echo [エラー] chienami-root-ca.crt が見つかりません。
    echo このバッチファイルと同じフォルダに証明書ファイルを置いてください。
    pause
    exit /b 1
)

echo.
echo === 1/2: hostsファイルへ名前解決を追加します ===
for %%H in (knowledge.lab.local auth.lab.local search.lab.local) do (
    findstr /c:"%%H" "%HOSTS_FILE%" >nul 2>&1
    if errorlevel 1 (
        echo %HOST_IP%  %%H>> "%HOSTS_FILE%"
        echo 追加しました: %%H
    ) else (
        echo 既に設定済みのためスキップ: %%H
    )
)

echo.
echo === 2/2: ルートCA証明書を信頼ストアへ登録します ===
certutil -addstore -f "ROOT" "%CERT_FILE%"
if %errorlevel% neq 0 (
    echo [エラー] 証明書の登録に失敗しました。
    pause
    exit /b 1
)

echo.
echo === 完了しました ===
echo ブラウザで https://knowledge.lab.local を開いて動作確認してください。
pause

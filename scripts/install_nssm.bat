@echo off
:: Tải nssm.exe (bản 64bit) và đặt vào thư mục dự án hoặc C:\\Windows\\System32 trước khi chạy script này
:: Thay đổi các đường dẫn dưới đây cho đúng với máy của bạn
set PYTHON_PATH=[YOUR_VALUE_PYTHON_PATH_VD_C:\\venv\\Scripts\\python.exe]
set PROJECT_DIR=[YOUR_VALUE_PROJECT_DIR_VD_C:\\toolsauto]
set NSSM_PATH=nssm.exe

echo Dang cai dat AI Generator Worker...
%NSSM_PATH% install AutoPub_AIGenerator "%PYTHON_PATH%" "%PROJECT_DIR%\\workers\\ai_generator.py"
%NSSM_PATH% set AutoPub_AIGenerator AppDirectory "%PROJECT_DIR%"
%NSSM_PATH% set AutoPub_AIGenerator AppStdout "%PROJECT_DIR%\\logs\\ai_generator.log"
%NSSM_PATH% set AutoPub_AIGenerator AppStderr "%PROJECT_DIR%\\logs\\ai_generator.log"
%NSSM_PATH% set AutoPub_AIGenerator AppRestartDelay 5000

echo Dang cai dat Publisher Worker...
%NSSM_PATH% install AutoPub_Publisher "%PYTHON_PATH%" "%PROJECT_DIR%\\workers\\publisher.py"
%NSSM_PATH% set AutoPub_Publisher AppDirectory "%PROJECT_DIR%"
%NSSM_PATH% set AutoPub_Publisher AppStdout "%PROJECT_DIR%\\logs\\publisher.log"
%NSSM_PATH% set AutoPub_Publisher AppStderr "%PROJECT_DIR%\\logs\\publisher.log"
%NSSM_PATH% set AutoPub_Publisher AppRestartDelay 5000

echo Dang cai dat Maintenance Worker...
%NSSM_PATH% install AutoPub_Maintenance "%PYTHON_PATH%" "%PROJECT_DIR%\\workers\\maintenance.py"
%NSSM_PATH% set AutoPub_Maintenance AppDirectory "%PROJECT_DIR%"
%NSSM_PATH% set AutoPub_Maintenance AppStdout "%PROJECT_DIR%\\logs\\maintenance.log"
%NSSM_PATH% set AutoPub_Maintenance AppStderr "%PROJECT_DIR%\\logs\\maintenance.log"
%NSSM_PATH% set AutoPub_Maintenance AppRestartDelay 5000

echo Dang cai dat Telegram Poller...
%NSSM_PATH% install AutoPub_Telegram "%PYTHON_PATH%" "%PROJECT_DIR%\\workers\\telegram_poller.py"
%NSSM_PATH% set AutoPub_Telegram AppDirectory "%PROJECT_DIR%"
%NSSM_PATH% set AutoPub_Telegram AppStdout "%PROJECT_DIR%\\logs\\telegram_poller.log"
%NSSM_PATH% set AutoPub_Telegram AppStderr "%PROJECT_DIR%\\logs\\telegram_poller.log"
%NSSM_PATH% set AutoPub_Telegram AppRestartDelay 5000

echo Hoan tat!
pause

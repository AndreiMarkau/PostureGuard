; ═══════════════════════════════════════════════════════════════════════════
; PostureGuard Inno Setup Script
; Requires: Inno Setup 7.x  https://jrsoftware.org/isinfo.php
;
; Как собрать установщик:
;   1. Установи Inno Setup 7:  https://jrsoftware.org/isdl.php
;   2. Собери PostureGuard.exe через build_exe.bat  (появится в dist\)
;   3. Запусти: iscc installer\PostureGuard_Setup.iss
;      — или открой этот файл в Inno Setup IDE и нажми Build → Compile
;   4. Готовый установщик: installer\Output\PostureGuard_Setup_1.0.0.exe
; ═══════════════════════════════════════════════════════════════════════════

#define AppName      "PostureGuard"
#define AppVersion   "1.0.0"
#define AppPublisher "PostureGuard"
#define AppURL       "https://github.com/your-repo/posture-guard"
#define AppExeName   "PostureGuard.exe"
#define AppMutex     "PostureGuardSingleInstance"

[Setup]
; Уникальный GUID приложения — НЕ менять после первого релиза
; (Windows использует его для распознавания обновлений)
AppId={{8F3A2C1D-4B5E-4F6A-9D2E-1C3B7A8F0E2D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}

; Mutex: если приложение запущено — Setup предложит его закрыть
AppMutex={#AppMutex}

; Лицензионное соглашение (показывается на отдельной странице)
LicenseFile=LICENSE.txt

; Папка по умолчанию: %ProgramFiles%\PostureGuard или %AppData%\PostureGuard
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Не требовать права администратора — ставится без UAC
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ── Выходной файл ──────────────────────────────────────────────────────────
OutputDir=Output
OutputBaseFilename=PostureGuard_Setup_{#AppVersion}
SetupIconFile=..\assets\app_icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}

; ── Сжатие ─────────────────────────────────────────────────────────────────
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; ── Внешний вид ────────────────────────────────────────────────────────────
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=no

; ── Метаданные исполняемого файла ──────────────────────────────────────────
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Setup
VersionInfoCopyright=Copyright (C) 2024 {#AppPublisher}
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}.0

; Минимальная ОС: Windows 10
MinVersion=10.0

; ── Режим обновления: тихо перезаписывает предыдущую версию ───────────────
CloseApplications=yes
CloseApplicationsFilter=*{#AppExeName}
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
; Русский
russian.CreateDesktopIcon=Создать значок на рабочем столе
russian.CreateStartupEntry=Запускать PostureGuard при входе в Windows
russian.LaunchAfterInstall=Запустить PostureGuard
russian.AppDescription=Приложение для контроля осанки через веб-камеру
russian.TasksHeader=Дополнительные задачи
russian.AlreadyRunning=PostureGuard сейчас запущен.%nЗакрыть его и продолжить установку?

; English
english.CreateDesktopIcon=Create a desktop shortcut
english.CreateStartupEntry=Launch PostureGuard when Windows starts
english.LaunchAfterInstall=Launch PostureGuard
english.AppDescription=Posture monitoring application with webcam tracking
english.TasksHeader=Additional tasks
english.AlreadyRunning=PostureGuard is currently running.%nClose it and continue setup?

[Tasks]
; Ярлык на рабочем столе (по умолчанию включён)
Name: "desktopicon"; \
     Description: "{cm:CreateDesktopIcon}"; \
     GroupDescription: "{cm:TasksHeader}"; \
     Flags: checkedonce

; Автозапуск при входе в систему (по умолчанию выключен)
Name: "startupentry"; \
     Description: "{cm:CreateStartupEntry}"; \
     GroupDescription: "{cm:TasksHeader}"; \
     Flags: unchecked

[Files]
; Основной исполняемый файл (собранный PyInstaller)
Source: "..\dist\{#AppExeName}";   DestDir: "{app}";          Flags: ignoreversion

; Конфиг по умолчанию — не перезаписывать при обновлении
Source: "..\config.json";           DestDir: "{app}";          Flags: ignoreversion onlyifdoesntexist

; Звуковой файл
Source: "..\assets\alert.wav";     DestDir: "{app}\assets";   Flags: ignoreversion

; Иконки
Source: "..\assets\app_icon.ico";  DestDir: "{app}\assets";   Flags: ignoreversion
Source: "..\assets\app_icon.svg";  DestDir: "{app}\assets";   Flags: ignoreversion

; Документация (доступна из меню Пуск, если нужно добавить ярлык)
Source: "..\README.md";            DestDir: "{app}";           Flags: ignoreversion

[Icons]
; ── Меню Пуск ──────────────────────────────────────────────────────────────
Name: "{group}\{#AppName}"; \
      Filename: "{app}\{#AppExeName}"; \
      Comment: "{cm:AppDescription}"; \
      IconFilename: "{app}\assets\app_icon.ico"

Name: "{group}\{cm:UninstallProgram,{#AppName}}"; \
      Filename: "{uninstallexe}"; \
      IconFilename: "{app}\assets\app_icon.ico"

; ── Рабочий стол (только если задача выбрана) ──────────────────────────────
Name: "{autodesktop}\{#AppName}"; \
      Filename: "{app}\{#AppExeName}"; \
      Comment: "{cm:AppDescription}"; \
      IconFilename: "{app}\assets\app_icon.ico"; \
      Tasks: desktopicon

[Registry]
; Автозапуск при входе в систему (только если задача выбрана)
Root: HKCU; \
      Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
      ValueType: string; \
      ValueName: "{#AppName}"; \
      ValueData: """{app}\{#AppExeName}"""; \
      Flags: uninsdeletevalue; \
      Tasks: startupentry

; Путь установки для диагностики
Root: HKCU; \
      Subkey: "Software\{#AppPublisher}\{#AppName}"; \
      ValueType: string; \
      ValueName: "InstallPath"; \
      ValueData: "{app}"; \
      Flags: uninsdeletekey

[Run]
; Предложить запустить после установки (галочка на последней странице)
Filename: "{app}\{#AppExeName}"; \
    Description: "{cm:LaunchAfterInstall}"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Закрыть приложение перед удалением (иначе файлы могут быть заблокированы)
Filename: "taskkill.exe"; \
    Parameters: "/F /IM {#AppExeName}"; \
    Flags: runhidden; \
    RunOnceId: "KillBeforeUninstall"

[UninstallDelete]
; Удалить пустые папки, оставшиеся после деинсталляции
Type: dirifempty; Name: "{app}\assets"
Type: dirifempty; Name: "{app}"

[Code]
// ─────────────────────────────────────────────────────────────────────────────
// InitializeSetup — проверить, не запущено ли приложение
// ─────────────────────────────────────────────────────────────────────────────
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if CheckForMutexes('{#AppMutex}') then
  begin
    if MsgBox(CustomMessage('AlreadyRunning'),
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      Exec('taskkill.exe', '/F /IM {#AppExeName}', '',
           SW_HIDE, ewWaitUntilTerminated, ResultCode);
      Sleep(1500);
    end
    else
      Result := False;
  end;
end;

// ─────────────────────────────────────────────────────────────────────────────
// InitializeWizard — кастомный текст на приветственной странице
// ─────────────────────────────────────────────────────────────────────────────
procedure InitializeWizard();
var
  NL: String;
begin
  NL := Chr(13) + Chr(10);
  if ActiveLanguage = 'english' then
  begin
    WizardForm.WelcomeLabel2.Caption :=
      'This will install PostureGuard {#AppVersion} on your computer.' +
      NL + NL +
      'PostureGuard monitors your posture via webcam and gently reminds you ' +
      'to sit up straight when you slouch or tilt your head forward.' +
      NL + NL +
      'System requirements:' +
      NL +
      '  - Windows 10 / 11 (64-bit)' +
      NL +
      '  - Webcam (USB or built-in)';
  end
  else
  begin
    WizardForm.WelcomeLabel2.Caption :=
      'Программа установит PostureGuard {#AppVersion} на ваш компьютер.' +
      NL + NL +
      'PostureGuard следит за осанкой через веб-камеру и мягко напоминает ' +
      'выпрямиться, когда вы сутулитесь или наклоняете голову вперёд.' +
      NL + NL +
      'Системные требования:' +
      NL +
      '  - Windows 10 / 11 (64-бит)' +
      NL +
      '  - Веб-камера (USB или встроенная)';
  end;
end;


#define MyAppName "Borsa Analiz Pro MAX"
#define MyAppVersion "4.2.1"
#define MyAppPublisher "V Software"
#define MyAppExeName "BorsaAnalizProMAX.exe"

[Setup]
AppId={{A83B4F11-7F95-4E9F-B6A5-123456789001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=SetupOutput
OutputBaseFilename=Setup_Borsa_Analiz_Pro_MAX_v4.2.1
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
LicenseFile=KULLANIM_KOSULLARI.txt
InfoBeforeFile=SORUMLULUK_REDDI.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "Masaüstüne kısayol oluştur"; GroupDescription: "Ek görevler:"

[Files]
Source: "dist\BorsaAnalizProMAX\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "KULLANIM_KOSULLARI.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "SORUMLULUK_REDDI.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "GIZLILIK_BILDIRIMI.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Borsa Analiz Pro MAX"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Borsa Analiz Pro MAX"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Borsa Analiz Pro MAX programını başlat"; Flags: nowait postinstall skipifsilent

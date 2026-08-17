; Inno Setup — Meshweave
; Compilar con: iscc scripts\Meshweave.iss
; Datos de usuario se crean en {commonappdata}\Meshweave (config, logs, state,
; backups, bin) — fuera de Program Files, sin permisos elevados en runtime.

#define MyAppName "Meshweave"
; build.ps1 pasa la versión con /DMyAppVersion=x.y.z; si no, este default.
#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif
#define MyAppExeName "Meshweave.exe"
#define MyAppId "com.meshweave.desktop"

[Setup]
AppId={{8F1E2C4B-7A6D-4E5F-9C3B-2A1D0E6F8B4A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Meshweave
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\dist\installer
OutputBaseFilename=Meshweave-Setup-x64
SetupIconFile=..\assets\meshweave.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
; ProgramData es escribible por usuarios estándar → no hace falta admin.
; (Si se requiere arrancar el túnel como servicio, eso se pide por separado.)

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\dist\Meshweave.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.example.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\cloudflared.example.yml"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; La app nunca escribe en {app}: solo se borra el ejecutable y ejemplos.
Type: filesandordirs; Name: "{app}"

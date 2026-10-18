; Inno Setup script: builds RealisticShotMaker-Setup.exe from the PyInstaller output.
#define AppName "RealisticShotMaker"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6B0C9E3E-7F2B-4C5E-9C1D-2A9E2D1B7F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=RealisticShotMaker
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=RealisticShotMaker-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
PrivilegesRequiredOverridesAllowed=dialog

[Files]
Source: "..\dist\RealisticShotMaker\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\RealisticShotMaker.exe"
Name: "{group}\{#AppName} Render Server"; Filename: "{app}\RealisticShotMaker.exe"; Parameters: "server"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\RealisticShotMaker.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Run]
Filename: "{app}\RealisticShotMaker.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent

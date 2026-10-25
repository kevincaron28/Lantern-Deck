; Inno Setup script for Lantern Deck (per-user install, no administrator rights).
; Built by build.ps1:  ISCC.exe /DVersion=3.0.0 installer\LanternDeck.iss
#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{8F3B0E4C-5B7A-4C1E-9C43-2A9E5D1F7A61}
AppName=Lantern Deck
AppVersion={#Version}
AppVerName=Lantern Deck {#Version}
AppPublisher=Lantern Deck contributors
AppPublisherURL=https://github.com/kevincaron28/Lantern-Deck
DefaultDirName={localappdata}\Programs\Lantern Deck
DefaultGroupName=Lantern Deck
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\outputs
OutputBaseFilename=Lantern-Deck-{#Version}-Setup
SetupIconFile=..\work\lantern.ico
UninstallDisplayIcon={app}\Lantern Deck.exe
UninstallDisplayName=Lantern Deck
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
LicenseFile=..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\outputs\dist\Lantern Deck\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Lantern Deck"; Filename: "{app}\Lantern Deck.exe"
Name: "{autodesktop}\Lantern Deck"; Filename: "{app}\Lantern Deck.exe"; Tasks: desktopicon

[Registry]
; Remove the optional "Start with Windows" entry on uninstall. Settings in
; %LOCALAPPDATA%\LanternDeck are kept so a reinstall keeps your deck.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Lantern Deck"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Lantern Deck.exe"; Description: "{cm:LaunchProgram,Lantern Deck}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM ""Lantern Deck.exe"" /F"; Flags: runhidden; RunOnceId: "StopLanternDeck"

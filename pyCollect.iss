[Setup]
AppName=pyCollect
AppVersion=1.0.0
AppPublisher=GE HealthCare
AppPublisherURL=https://www.gehealthcare.com
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\pyCollect
OutputDir=.
OutputBaseFilename=pyCollect_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\pyCollect.exe

[Dirs]
Name: "{userappdata}\Local\pyCollect"
Name: "{userappdata}\Local\pyCollect\output"

[Files]
Source: "dist\pyCollect.exe"; DestDir: "{app}"
Source: "README.md"; DestDir: "{app}"
Source: "assets\icon.ico"; DestDir: "{app}"

[Icons]
Name: "{commonprograms}\pyCollect"; Filename: "{app}\pyCollect.exe"; IconFilename: "{app}\icon.ico"
Name: "{commondesktop}\pyCollect"; Filename: "{app}\pyCollect.exe"; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\pyCollect.exe"; Description: "{cm:LaunchProgram,pyCollect}"; Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\Local\pyCollect"

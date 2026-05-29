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
Name: "{localappdata}\pyCollect"
Name: "{localappdata}\pyCollect\output"
Name: "{app}\config"

[Files]
Source: "dist\pyCollect.exe"; DestDir: "{app}"
Source: "dist\pyCollect-cli.exe"; DestDir: "{app}"
Source: "pyCollect.pdf"; DestDir: "{app}"
Source: "assets\icon.ico"; DestDir: "{app}"
Source: "config\pycollect_gui_config.default.json"; DestDir: "{app}\config"
Source: "config\params5.txt"; DestDir: "{app}\config"
Source: "config\waves5.txt"; DestDir: "{app}\config"
Source: "Example.drc"; DestDir: "{app}"
Source: "Example.txt"; DestDir: "{app}"
Source: "config\pycollect_gui_config.default.json"; DestDir: "{localappdata}\pyCollect"; DestName: "pycollect_gui_config.json"; Flags: onlyifdoesntexist
Source: "config\params5.txt"; DestDir: "{localappdata}\pyCollect"; Flags: onlyifdoesntexist
Source: "config\waves5.txt"; DestDir: "{localappdata}\pyCollect"; Flags: onlyifdoesntexist
Source: "Example.drc"; DestDir: "{localappdata}\pyCollect"; Flags: onlyifdoesntexist

[Icons]
Name: "{userprograms}\pyCollect"; Filename: "{app}\pyCollect.exe"; IconFilename: "{app}\icon.ico"
Name: "{userdesktop}\pyCollect"; Filename: "{app}\pyCollect.exe"; IconFilename: "{app}\icon.ico"

[Run]
Filename: "{app}\pyCollect.exe"; Description: "{cm:LaunchProgram,pyCollect}"; Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\pyCollect"

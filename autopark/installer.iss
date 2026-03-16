[Setup]
AppName=АвтоПарк — Помощник механика
AppVersion=1.0.0
DefaultDirName={autopf}\AutoPark
DefaultGroupName=АвтоПарк
OutputBaseFilename=AutoPark_Setup
OutputDir=dist\installer
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительно:"

[Files]
Source: "dist\AutoPark.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "credentials\google_service_account.json"; DestDir: "{app}\credentials"; Flags: skipifsourcedoesntexist
Source: "data\*"; DestDir: "{app}\data"; Flags: recursesubdirs createallsubdirs

[Dirs]
Name: "{app}\data\pdfs"
Name: "{app}\data\chroma_db"
Name: "{app}\credentials"

[Icons]
Name: "{group}\АвтоПарк"; Filename: "{app}\AutoPark.exe"
Name: "{commondesktop}\АвтоПарк"; Filename: "{app}\AutoPark.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AutoPark.exe"; Description: "Запустить АвтоПарк"; Flags: postinstall nowait skipifsilent

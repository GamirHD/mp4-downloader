; Windows-Installer: Programm mit Oberfläche + Befehl "vd" in einem Paket.
; Bauen mit build-windows.ps1 (Version per /DMyAppVersion=x.y.z).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Video-Downloader"
#define MyAppPublisher "GamirHD"
#define MyAppExeName "mp4-downloader.exe"

[Setup]
AppId={{57B47A34-65C3-44DA-B6A9-2F064D6F726D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/GamirHD/mp4-downloader
; Ohne Administratorrechte installieren (nach %LOCALAPPDATA%\Programs)
PrivilegesRequired=lowest
DefaultDirName={autopf}\mp4-downloader
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ChangesEnvironment=yes
CloseApplications=yes
OutputDir=dist
OutputBaseFilename=mp4-downloader-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\mp4-downloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Programmdateien einer älteren Version entfernen, damit nichts Veraltetes liegen bleibt
Type: filesandordirs; Name: "{app}\_internal"
; Reste der früheren Installation über install.ps1/pip
Type: filesandordirs; Name: "{localappdata}\mp4-downloader"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Befehl "vd" in jedem neuen Terminal verfügbar machen
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{cmd}"; Parameters: "/C python -m pip uninstall -y mp4-downloader"; StatusMsg: "Entferne alte Version..."; Flags: runhidden waituntilterminated; Check: HasOldPipVersion
Filename: "{cmd}"; Parameters: "/C winget install --id Gyan.FFmpeg --exact --source winget --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Installiere ffmpeg..."; Flags: runhidden waituntilterminated; Check: NeedsFfmpeg
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function CommandSucceeds(const Command: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C ' + Command, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function NeedsFfmpeg: Boolean;
begin
  Result := not CommandSucceeds('where ffmpeg');
end;

function HasOldPipVersion: Boolean;
begin
  Result := CommandSucceeds('python -m pip show mp4-downloader');
end;

function NeedsAddPath(Dir: String): Boolean;
var
  Paths: String;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') = 0;
end;

procedure RemoveFromPath(Dir: String);
var
  Paths: String;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths) then
    exit;
  Paths := ';' + Paths + ';';
  P := Pos(';' + Uppercase(Dir) + ';', Uppercase(Paths));
  if P = 0 then
    exit;
  Delete(Paths, P, Length(Dir) + 1);
  while (Length(Paths) > 0) and (Paths[1] = ';') do
    Delete(Paths, 1, 1);
  while (Length(Paths) > 0) and (Paths[Length(Paths)] = ';') do
    Delete(Paths, Length(Paths), 1);
  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', Paths);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    RemoveFromPath(ExpandConstant('{app}'));
    DataDir := ExpandConstant('{userappdata}\mp4-downloader');
    if DirExists(DataDir) and (SuppressibleMsgBox(
      'Sollen auch Einstellungen, Download-Verlauf und gespeicherte Logins gelöscht werden?',
      mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES) then
      DelTree(DataDir, True, True, True);
  end;
end;

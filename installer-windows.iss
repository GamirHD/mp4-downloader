; Windows installer: window app + command "vd" in one package (English and German).
; Build with build-windows.ps1 (version via /DMyAppVersion=x.y.z).

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Video Downloader"
#define MyAppPublisher "GamirHD"
#define MyAppExeName "mp4-downloader.exe"

[Setup]
AppId={{57B47A34-65C3-44DA-B6A9-2F064D6F726D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/GamirHD/mp4-downloader
; Install without administrator rights (to %LOCALAPPDATA%\Programs)
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
ShowLanguageDialog=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[CustomMessages]
english.RemovingOld=Removing old version...
german.RemovingOld=Entferne alte Version...
english.InstallingFfmpeg=Installing ffmpeg...
german.InstallingFfmpeg=Installiere ffmpeg...
english.DeleteData=Also delete settings, download history and saved logins?
german.DeleteData=Sollen auch Einstellungen, Download-Verlauf und gespeicherte Logins gelöscht werden?

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\mp4-downloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Remove program files of an older version so nothing outdated is left behind
Type: filesandordirs; Name: "{app}\_internal"
; Leftovers of the earlier installation via install.ps1/pip
Type: filesandordirs; Name: "{localappdata}\mp4-downloader"
; Shortcuts of version 1.1-1.3 (named "Video-Downloader")
Type: filesandordirs; Name: "{userprograms}\Video-Downloader"
Type: files; Name: "{userdesktop}\Video-Downloader.lnk"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Make the command "vd" available in every new terminal
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{cmd}"; Parameters: "/C python -m pip uninstall -y mp4-downloader"; StatusMsg: "{cm:RemovingOld}"; Flags: runhidden waituntilterminated; Check: HasOldPipVersion
Filename: "{cmd}"; Parameters: "/C winget install --id Gyan.FFmpeg --exact --source winget --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "{cm:InstallingFfmpeg}"; Flags: runhidden waituntilterminated; Check: NeedsFfmpeg
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
    if DirExists(DataDir) and (SuppressibleMsgBox(CustomMessage('DeleteData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES) then
      DelTree(DataDir, True, True, True);
  end;
end;

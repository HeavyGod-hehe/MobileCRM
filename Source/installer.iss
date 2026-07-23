; Phone Reseller CRM — Windows installer (Inno Setup)
;
; Do not run ISCC on this directly by hand unless you already have a fresh
; PyInstaller onedir build at dist\Phone Reseller CRM\ (from
; PhoneResellerCRM-win.spec) — use build_installer.py instead, which runs
; the full pipeline (PyInstaller -> this compiler -> checksum) in one shot:
;
;   python build_installer.py
;
; Manual equivalent, if you already have a fresh dist\ build:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
;
; Per-user install (PrivilegesRequired=lowest) — shopkeepers running this
; don't have admin rights, and none should be required. Installs to
; %LOCALAPPDATA%\Phone Reseller CRM\Phone Reseller CRM\ (the nested
; "Phone Reseller CRM" subfolder is deliberate: it matches the exact layout
; update_service.py's self-updater already resolves paths against — see the
; docstring on _resolve_target() in update_service.py — so installs made by
; this installer can self-update exactly like existing customer copies,
; with zero path-resolution risk).

#define MyAppName "Phone Reseller CRM"
#define MyAppPublisher "Phone Reseller CRM"
#define MyAppExeName "Phone Reseller CRM.exe"
#define MyAppVersion Trim(FileRead(FileOpen(SourcePath + "VERSION")))

[Setup]
AppId={{893F8DD3-4915-47A7-B139-1CB2BDA74BA6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
OutputDir=releases
OutputBaseFilename=PhoneResellerCRM-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppName}\{#MyAppExeName}
MinVersion=10.0
ArchitecturesInstallIn64BitMode=x64compatible
; No SetupIconFile/custom wizard image on purpose - no icon asset exists
; anywhere in this repo yet (searched thoroughly). Flagged separately;
; Inno's own default icon is used until a real one is supplied.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: checkedonce

[Files]
; The entire onedir PyInstaller output (exe + _internal\), unchanged.
; Nothing under Data\ is ever part of this - a fresh build never has one.
Source: "dist\{#MyAppName}\*"; DestDir: "{app}\{#MyAppName}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppName}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppName}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppName}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Deliberately NO [UninstallDelete] entries for Data\ (or anything inside
; it) - Inno's uninstaller only ever removes what it itself installed
; (tracked in [Files] above) plus directories it created that are empty. A
; runtime-created Data\ folder full of the customer's database/backups was
; never installed by Setup and is never touched by Uninstall, with no
; special-casing needed - this is Inno's default behavior, kept default on
; purpose.

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataPath: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataPath := ExpandConstant('{app}\{#MyAppName}\Data');
    if DirExists(DataPath) then
      MsgBox('Phone Reseller CRM has been removed.' + #13#10 + #13#10 +
        'Your business data was kept at:' + #13#10 + DataPath,
        mbInformation, MB_OK)
    else
      MsgBox('Phone Reseller CRM has been removed.', mbInformation, MB_OK);
  end;
end;

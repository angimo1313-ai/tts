; Voice Studio — Inno Setup 설치 스크립트
; 빌드: Inno Setup(https://jrsoftware.org/isdl.php) 설치 후
;       ISCC.exe installer\VoiceStudio.iss  실행 → installer\Output\VoiceStudio-Setup.exe 생성
;
; 설계: 소스 코드만 설치(수 MB). 무거운 환경(.venv, 모델 수 GB)은 설치 마지막에
;       setup.ps1 이 인터넷에서 구성. 관리자 권한 불필요(사용자 폴더 설치).

#define AppName "Voice Studio"
#define AppVersion "0.1.0"
#define AppPublisher "Voice Studio"

[Setup]
AppId={{9F5B2E10-6C4A-4E3B-9A21-VOICESTUDIO01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\Voice Studio
DefaultGroupName=Voice Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=VoiceStudio-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\app\static\icon.ico
UninstallDisplayIcon={app}\app\static\icon.ico

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 만들기"; GroupDescription: "추가 작업:"
Name: "runsetup"; Description: "지금 환경 설치 (인터넷 필요, 수 GB 다운로드 · 수십 분)"; GroupDescription: "설치 후:"
Name: "sovits"; Description: "한국어 엔진(GPT-SoVITS)도 함께 설치"; GroupDescription: "설치 후:"; Flags: unchecked

[Files]
; 소스 일체 복사 — 대용량/생성물/클론레포는 제외
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; \
  Excludes: "\.venv\*,\.venv-sovits\*,\engines\GPT-SoVITS\*,\outputs\*.wav,\outputs\history.jsonl,\data\raw\*,\data\datasets\*,\data\voices\*,\tools\ffmpeg\*,\.git\*,\installer\Output\*,__pycache__\*,*.pyc"

[Icons]
Name: "{group}\Voice Studio"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\app\static\icon.ico"
Name: "{userdesktop}\Voice Studio"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\app\static\icon.ico"; Tasks: desktopicon

[Run]
; 환경 설치 (선택). -SoVITS 여부는 sovits 태스크로 분기.
Filename: "powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\setup.ps1"" {code:GetSoVITSFlag}"; \
  WorkingDir: "{app}"; StatusMsg: "환경을 설치하는 중입니다 (수십 분 소요될 수 있습니다)..."; \
  Flags: runhidden waituntilterminated; Tasks: runsetup

[Code]
function GetSoVITSFlag(Param: String): String;
begin
  if WizardIsTaskSelected('sovits') then
    Result := '-SoVITS'
  else
    Result := '';
end;

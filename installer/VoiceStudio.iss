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
AppId={{9F5B2E10-6C4A-4E3B-9A21-3D5E7F9A1B2C}
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
Name: "runsetup"; Description: "설치 후 바로 '환경 설치' 시작 (인터넷 필요, 수 GB · 수십 분)"; GroupDescription: "설치 후:"
Name: "sovits"; Description: "한국어 엔진(GPT-SoVITS)도 함께 설치"; GroupDescription: "설치 후:"

[Files]
; 소스 일체 복사 — 대용량/생성물/클론레포는 제외
Source: "..\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion; \
  Excludes: "\.venv\*,\.venv-sovits\*,\.uvhome\*,\.appprofile\*,\engines\GPT-SoVITS\*,\outputs\*.wav,\outputs\history.jsonl,\data\raw\*,\data\datasets\*,\data\voices\*,\tools\ffmpeg\*,github_token.txt,\.git\*,\installer\Output\*,__pycache__\*,*.pyc"

[Icons]
; 앱 실행 (환경 설치 후 동작). 콘솔 없이 pythonw 로 런처 실행.
Name: "{group}\Voice Studio"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\app\static\icon.ico"
Name: "{userdesktop}\Voice Studio"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\launcher.pyw"""; WorkingDir: "{app}"; IconFilename: "{app}\app\static\icon.ico"; Tasks: desktopicon
; 환경 설치 (최초 1회, 진행상황 보임). 다운로드 실패 시 이 아이콘으로 재시도.
; setup-nouv.ps1 = uv 없이 python.org+venv+pip 설치 → 클라우드PC/VDI 등 까다로운 환경 포함 어디서나 동작.
Name: "{group}\환경 설치 (최초 1회)"; Filename: "powershell.exe"; Parameters: "-ExecutionPolicy Bypass -NoProfile -NoExit -File ""{app}\setup-nouv.ps1"" -SoVITS"; WorkingDir: "{app}"; IconFilename: "{app}\app\static\icon.ico"

[Run]
; 설치 직후 환경 설치를 '보이는' PowerShell 창으로 시작(선택). nowait 로 위저드는 바로 종료.
Filename: "powershell.exe"; \
  Parameters: "-ExecutionPolicy Bypass -NoProfile -NoExit -File ""{app}\setup-nouv.ps1"" {code:GetSoVITSFlag}"; \
  WorkingDir: "{app}"; Description: "환경 설치 시작"; \
  Flags: postinstall nowait skipifsilent; Tasks: runsetup

[Code]
function GetSoVITSFlag(Param: String): String;
begin
  if WizardIsTaskSelected('sovits') then
    Result := '-SoVITS'
  else
    Result := '';
end;

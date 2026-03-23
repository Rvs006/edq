!macro customInit
  ; Check if Docker is installed
  nsExec::ExecToStack 'docker --version'
  Pop $0
  ${If} $0 != 0
    MessageBox MB_YESNO|MB_ICONEXCLAMATION \
      "Docker Desktop is required but was not detected.$\r$\n$\r$\nWould you like to download Docker Desktop?" \
      IDYES downloadDocker IDNO skipDocker
    downloadDocker:
      ExecShell "open" "https://www.docker.com/products/docker-desktop/"
    skipDocker:
  ${EndIf}
!macroend

!macro customInstall
  ; Create desktop shortcut
  CreateShortCut "$DESKTOP\EDQ.lnk" "$INSTDIR\EDQ.exe" "" "$INSTDIR\EDQ.exe" 0
!macroend

!macro customUnInstall
  ; Remove desktop shortcut
  Delete "$DESKTOP\EDQ.lnk"
!macroend

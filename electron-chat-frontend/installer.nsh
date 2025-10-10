; NSIS安装程序自定义脚本

!macro preInit
  ; 检查是否已经有实例在运行
  System::Call 'kernel32::CreateMutex(i 0, i 0, t "AI-Chat-Installer") i .r1 ?e'
  Pop $R0
  StrCmp $R0 0 +3
    MessageBox MB_OK|MB_ICONEXCLAMATION "安装程序已经在运行中！"
    Abort
!macroend

!macro customInstall
  ; 创建开始菜单文件夹
  CreateDirectory "$SMPROGRAMS\12345智能助手"
  
  ; 创建桌面快捷方式
  CreateShortCut "$DESKTOP\12345智能助手.lnk" "$INSTDIR\12345智能助手.exe"
  
  ; 写入注册表信息
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\12345智能助手" "DisplayName" "12345智能助手"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\12345智能助手" "UninstallString" "$INSTDIR\Uninstall 12345智能助手.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\12345智能助手" "DisplayIcon" "$INSTDIR\12345智能助手.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\12345智能助手" "Publisher" "12345智能助手 Team"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\12345智能助手" "DisplayVersion" "${VERSION}"
  
  ; 关联文件类型（可选）
  ; WriteRegStr HKCR ".chat" "" "AI.Chat.File"
  ; WriteRegStr HKCR "AI.Chat.File" "" "12345智能助手 File"
  ; WriteRegStr HKCR "AI.Chat.File\DefaultIcon" "" "$INSTDIR\12345智能助手.exe,0"
!macroend

!macro customUnInstall
  ; 删除注册表项
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\12345智能助手"
  
  ; 删除快捷方式
  Delete "$DESKTOP\12345智能助手.lnk"
  Delete "$SMPROGRAMS\12345智能助手\12345智能助手.lnk"
  RMDir "$SMPROGRAMS\12345智能助手"
  
  ; 删除用户数据（可选，谨慎使用）
  ; RMDir /r "$APPDATA\12345智能助手"
!macroend

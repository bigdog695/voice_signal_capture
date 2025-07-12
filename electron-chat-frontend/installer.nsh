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
  CreateDirectory "$SMPROGRAMS\AI Chat"
  
  ; 创建桌面快捷方式
  CreateShortCut "$DESKTOP\AI Chat.lnk" "$INSTDIR\AI Chat.exe"
  
  ; 写入注册表信息
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Chat" "DisplayName" "AI Chat"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Chat" "UninstallString" "$INSTDIR\Uninstall AI Chat.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Chat" "DisplayIcon" "$INSTDIR\AI Chat.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Chat" "Publisher" "AI Chat Team"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Chat" "DisplayVersion" "${VERSION}"
  
  ; 关联文件类型（可选）
  ; WriteRegStr HKCR ".chat" "" "AI.Chat.File"
  ; WriteRegStr HKCR "AI.Chat.File" "" "AI Chat File"
  ; WriteRegStr HKCR "AI.Chat.File\DefaultIcon" "" "$INSTDIR\AI Chat.exe,0"
!macroend

!macro customUnInstall
  ; 删除注册表项
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI Chat"
  
  ; 删除快捷方式
  Delete "$DESKTOP\AI Chat.lnk"
  Delete "$SMPROGRAMS\AI Chat\AI Chat.lnk"
  RMDir "$SMPROGRAMS\AI Chat"
  
  ; 删除用户数据（可选，谨慎使用）
  ; RMDir /r "$APPDATA\AI Chat"
!macroend

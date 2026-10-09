; resources\livros é um atalho de pasta (junção) para a biblioteca do usuário, em %APPDATA%\Estante\livros.
; Antes de o desinstalador apagar a pasta do programa (também ao atualizar), sai só o atalho: sem isto ele poderia seguir por ele e apagar os livros.
; rmdir sem /s tira a junção e não toca no que está do outro lado; numa pasta de verdade com conteúdo, não faz nada.
!macro customUnInit
  nsExec::Exec 'cmd /c rmdir "$INSTDIR\resources\livros"'
!macroend

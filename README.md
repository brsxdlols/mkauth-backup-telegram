# Backup Telegram para MK-AUTH

Addon desenvolvido para configurar o envio automático do backup MK-AUTH ao Telegram pelo menu **Provedor → Backup Telegram**.

## Recursos

- Busca de chats pelo token digitado, seleção de grupo ou conversa e guia de criação do bot. A busca não salva o destino automaticamente, não remove webhooks e não confirma ou apaga atualizações do bot.


- Token oculto por padrão; visualização mediante senha validada no servidor, Chat ID e nome do MK-AUTH na tela de configuração.
- Ativação/desativação imediata e horário diário configurável.
- Teste de integração: valida o bot, consulta o chat e envia uma mensagem de confirmação.
- Envio imediato e opção de salvar e enviar agora.
- Modal em todas as operações; porcentagem real durante upload e indicador animado nas demais ações.
- Download ao clicar no nome do backup mais recente.
- Teste de integridade da compressão bzip2 e cálculo SHA-256.
- Histórico limitado aos últimos 100 registros.

## Requisitos

Linux com MK-AUTH em `/opt/mk-auth`, PHP CLI 7.3 ou superior e PHP web 7.1 ou superior, extensões curl/json/mysqli/posix, Python 3.6 ou superior, sudo/visudo, cron, bzip2 e timeout. A instalação pela internet requer curl e tar. O usuário do servidor web deve ser `www-data`.

O addon usa a autenticação nativa e exige `sis_perm.perm_backup = sim` para o operador. Não amplia as permissões de usuários ou grupos. A conexão ao banco é obtida da configuração nativa `/opt/mk-auth/include/conexao.php`; não há senha de banco no pacote. Não depende do relatório de clientes offline.

## Instalação ou atualização

Como root, baixe o instalador e execute:

```bash
curl -fsSL https://raw.githubusercontent.com/brsxdlols/mkauth-backup-telegram/v1.5.2/instalar.sh -o /root/instalar-backup-telegram.sh
bash /root/instalar-backup-telegram.sh
```

Também é possível baixar o código da versão, extrair e executar `bash install.sh` na pasta extraída. Para validar os hashes e a sintaxe sem instalar, execute `bash install.sh --check`.

O instalador verifica o pacote, guarda os arquivos substituídos e restaura os arquivos alterados se houver falha durante a instalação. Atualizações preservam a configuração salva. O menu é atualizado sem duplicar o atalho.

### Migração da rotina antiga

Quando existe `/opt/mk-auth/scripts/enviaBkp`, o instalador tenta importar token, Chat ID e nome, sem executar o script ou imprimir os valores. Agendamentos diários em `/etc/crontab` são migrados para o novo serviço. O script antigo permanece no servidor; a linha antiga fica comentada para impedir dois envios.

Se houver uma rotina diferente, múltiplos agendamentos ou configuração não reconhecida, a instalação é interrompida e as alterações são revertidas. A instalação nova começa com o envio desativado. Na migração, o novo agendamento não repete automaticamente o envio no dia da instalação; o botão de envio imediato continua disponível.

## Uso

1. Abra **Provedor → Backup Telegram**.
2. Informe token, Chat ID e nome; defina o horário e salve.
3. Use **Sincronizar e testar integração**. Em conversa privada, inicie o bot antes. Em grupos, adicione o bot e permita o envio de documentos.
4. Use **Testar integridade do backup** e **Enviar backup agora** quando desejar.

O token salvo não é enviado no carregamento da página nem na consulta de status. Somente operadores com permissão de backup e a senha do usuário conectado ao MK-AUTH podem visualizá-lo. A exibição dura 30 segundos, e cinco senhas incorretas bloqueiam novas tentativas por cinco minutos. Substituir o token continua permitido sem a senha extra. O serviço não inclui tokens nem respostas brutas do Telegram no histórico. O envio usa o horário configurado no PHP do servidor, que deve corresponder ao horário local desejado.

## O que é testado

O teste executa `bzip2 -t` no arquivo mais recente e calcula seu SHA-256. Detecta problemas na compressão e recusa arquivos que mudaram durante o teste. **Não valida a possibilidade de restaurar o banco, a completude dos dados nem backups criptografados internamente.** Uma restauração em ambiente separado é necessária para essa validação.

O addon envia arquivos já gerados pelo MK-AUTH; ele não cria backups. O envio via API pública do Telegram fica limitado a 50 MB. Arquivos vazios ou criados há menos de dois minutos são recusados. Há trava para impedir operações simultâneas; erros agendados ficam no histórico e podem ser reenviados manualmente.

## Arquivos e retenção

| Local | Uso |
| --- | --- |
| `/opt/mk-auth/admin/addons/backup_telegram/` | Interface |
| `/usr/local/lib/mka-backup-telegram/service.php` | Serviço root com operações fixas |
| `/var/lib/mka-backup-telegram/` | Configuração e histórico, acesso root |
| `/etc/sudoers.d/mka-backup-telegram` | Autoriza somente o comando fixo do serviço (também no bloco gerenciado de `/etc/sudoers`) |
| `/etc/cron.d/mka-backup-telegram` | Verifica a execução diária a cada minuto |

Configuração e histórico ficam fora da pasta pública, com arquivos `600` em diretório `700`. O instalador conserva **5 snapshots** de instalação sob `install-backups`, com índice `rollback.json`; só esses snapshots próprios são elegíveis para retenção. Não remove backups `.maz`, nem modifica dados ou logs do RADIUS/MySQL. O serviço não mantém cópias locais adicionais dos backups.

## Validação e origem

A versão 1.5.2 foi preparada a partir do addon usado no Visual Net. Os testes de instalação usam uma árvore temporária isolada; não acionam envio nem restauração. Credenciais, configurações e arquivos de backup de produção não são distribuídos.

## Confirmação para visualizar o token

A visualização exige a senha do próprio usuário conectado ao MK-AUTH, a conta ativa e a permissão de backup. A verificação segue a transformação SHA-256 da tela de login nativa e a validação bcrypt. Não é criada senha separada, e nenhuma senha do MK-AUTH é alterada.

## Compatibilidade e proteção do serviço

A versão 1.5.2 suporta PHP 7.3 e 8.x e não altera o PHP padrão do servidor. As chamadas de processos são convertidas em comandos com argumentos individualmente escapados, compatíveis com PHP 7.3. O instalador mostra a versão detectada e informa requisitos ausentes.

Em MK-AUTH com os perfis AppArmor nativos ativos, instala um perfil dedicado ao serviço e uma transição específica; não desativa o AppArmor nem remove a proteção de rede dos processos web. O perfil permite leitura dos backups e configuração nativa, gravação no diretório privado do addon e comunicação de rede do serviço. O comando autorizado fica registrado no arquivo principal de sudoers, dentro de um bloco identificado, para resistir à recriação de sudoers.d.

### Correções da versão 1.5.2

- Detecta também o AppArmor antigo do Apache (`apache2//admin`) e configura a transição para o serviço dedicado.
- Mantém a regra sudo restrita ao comando do serviço e as configurações locais.
- Envia os métodos comuns do Telegram como formulário URL-encoded; somente o envio de arquivos usa multipart. Isso evita o timeout causado por POST vazio em versões antigas do cURL/PHP 7.3.
- Compatibilidade da interface validada em ambiente com PHP web 7.1.1 e serviço CLI 7.3.31.

### Detecção automática do PHP — v1.5.2

O instalador verifica o PHP do PATH e os executáveis versionados em `/usr/bin`, `/usr/local/bin`, `/opt/php*/bin/php` e `/opt/mk-auth/hhvm/*/bin/php`. Seleciona a versão compatível mais recente com todas as extensões necessárias e usa esse mesmo caminho para validação, serviço, sudoers, AppArmor e cron.

Assim, se o comando `php` aponta para 7.1.1, mas há 7.3 ou 8.x instalado, não é necessário alterar o PATH nem os links do sistema. A detecção é somente de leitura: não instala outro PHP e não altera o PHP padrão do MK-AUTH. Se nenhum candidato for compatível, exibe as razões antes de alterar a instalação.

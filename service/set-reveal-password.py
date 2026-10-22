#!/usr/bin/env python3
"""Define uma senha local de visualização, sem embutir segredo no pacote."""
import getpass
import json
import os
import pathlib
import subprocess
import tempfile

if os.geteuid() != 0:
    raise SystemExit('Execute como root.')
password = getpass.getpass('Nova senha para visualizar o token: ')
if len(password) < 8:
    raise SystemExit('Use pelo menos 8 caracteres.')
if password != getpass.getpass('Confirme a senha: '):
    raise SystemExit('As senhas não coincidem.')
result = subprocess.run(['php', '-r', 'echo password_hash(stream_get_contents(STDIN), PASSWORD_DEFAULT);'], input=password.encode(), stdout=subprocess.PIPE, check=True)
folder = pathlib.Path('/var/lib/mka-backup-telegram')
folder.mkdir(mode=0o700, exist_ok=True)
fd, temporary = tempfile.mkstemp(dir=str(folder))
with os.fdopen(fd, 'w') as stream:
    json.dump({'reveal_hash': result.stdout.decode()}, stream)
os.chmod(temporary, 0o600)
os.replace(temporary, str(folder / 'security.json'))
attempts = folder / 'reveal-attempts.json'
if attempts.exists():
    attempts.unlink()
print('Senha de visualização definida. O token e o agendamento foram preservados.')

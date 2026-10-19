#!/usr/bin/env python3
"""Instalação local, atualização idempotente e rollback sem segredos no pacote."""
import argparse
import datetime
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

SOURCE = pathlib.Path(__file__).resolve().parent
WEB = '/opt/mk-auth/admin/addons/backup_telegram'
DATA = '/var/lib/mka-backup-telegram'
SERVICE = '/usr/local/lib/mka-backup-telegram/service.php'
MENU_BEGIN = '// BACKUP TELEGRAM INICIO'
MENU_END = '// BACKUP TELEGRAM FIM'
MENU = MENU_BEGIN + '\nadd_menu.provedor(JSON.stringify({plink: window.location.origin + "/admin/addons/backup_telegram/", ptext: "<b>Backup Telegram</b>"}));\n' + MENU_END


def verify():
    for line in (SOURCE / 'SHA256SUMS').read_text().splitlines():
        expected, name = line.split('  ', 1)
        path = (SOURCE / name).resolve()
        if SOURCE not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Pacote inválido ou alterado: ' + name)
    for name in ['addon/index.php', 'service/service.php']:
        subprocess.run(['php', '-l', str(SOURCE / name)], check=True, stdout=subprocess.DEVNULL)


def install(prefix):
    def target(name):
        return prefix / name.lstrip('/')

    for name in ['/opt/mk-auth/include/addons.inc.hhvm', '/opt/mk-auth/include/conexao.php', '/opt/mk-auth/admin/addons/addon.js', '/etc/crontab']:
        if not target(name).is_file():
            raise RuntimeError('Arquivo necessário não encontrado: ' + name)
    for directory in [DATA, WEB, '/usr/local/lib/mka-backup-telegram', '/etc/sudoers.d', '/etc/cron.d']:
        path = target(directory)
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(str(path), 0o700 if directory == DATA else 0o755)
        if directory in [DATA, WEB, '/usr/local/lib/mka-backup-telegram']:
            os.chown(str(path), 0, 0)

    # Only snapshots made by this installer are eligible for retention.
    backups = target(DATA + '/install-backups')
    backups.mkdir(mode=0o700, exist_ok=True)
    snapshot = pathlib.Path(tempfile.mkdtemp(prefix='install-', dir=str(backups)))
    records = []

    def put(name, content, mode=0o644):
        path = target(name)
        if path.is_symlink():
            raise RuntimeError('Destino inesperado (link simbólico): ' + name)
        if path.exists() and path.read_bytes() == content and (path.stat().st_mode & 0o777) == mode:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = None
        oldmode = None
        if path.exists():
            previous = snapshot / str(len(records))
            shutil.copy2(str(path), str(previous))
            oldmode = path.stat().st_mode & 0o777
        records.append((path, previous, oldmode))
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
            os.chmod(tmp, mode)
            os.replace(tmp, str(path))
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    try:
        cronpath = target('/etc/crontab')
        cron = cronpath.read_text()
        old_lines = [line for line in cron.splitlines() if not line.lstrip().startswith('#') and '/opt/mk-auth/scripts/enviaBkp' in line]
        if len(old_lines) > 1:
            raise RuntimeError('Mais de um agendamento legado encontrado. Resolva a duplicação antes de instalar.')
        # Do not silently override an alternative cron installation.
        candidates = list(target('/etc/cron.d').glob('*')) + [target('/var/spool/cron/crontabs/root')]
        for path in candidates:
            if path.is_file() and path.name != 'mka-backup-telegram':
                if any('/opt/mk-auth/scripts/enviaBkp' in line and not line.lstrip().startswith('#') for line in path.read_text(errors='replace').splitlines()):
                    raise RuntimeError('Agendamento legado fora de /etc/crontab: ' + str(path))
        cfgpath = target(DATA + '/config.json')
        if not cfgpath.exists():
            values = {}
            legacy = target('/opt/mk-auth/scripts/enviaBkp')
            if legacy.is_file():
                for line in legacy.read_text(errors='replace').splitlines():
                    match = re.match(r"^\s*(TOKEN|BOT_TOKEN|CHAT_ID|USER|MK_NOME)\s*=\s*(['\"])(.*?)\2\s*$", line)
                    if match:
                        values[match.group(1)] = match.group(3)
            token = values.get('TOKEN') or values.get('BOT_TOKEN', '')
            chat = values.get('CHAT_ID') or values.get('USER', '')
            hour, minute = '06', '30'
            if old_lines:
                fields = old_lines[0].split()
                if len(fields) < 7 or not fields[0].isdigit() or not fields[1].isdigit() or fields[2:5] != ['*', '*', '*'] or fields[5] != 'root':
                    raise RuntimeError('Agendamento legado não é diário. Migração automática interrompida.')
                minute, hour = fields[0].zfill(2), fields[1].zfill(2)
                if not 0 <= int(hour) <= 23 or not 0 <= int(minute) <= 59:
                    raise RuntimeError('Horário legado inválido.')
            config = dict(token=token, chat=chat, name=values.get('MK_NOME', 'MK-AUTH'), time=hour+':'+minute, enabled=bool(old_lines and token and chat))
            if old_lines and not (token and chat):
                raise RuntimeError('Credenciais legadas não puderam ser importadas. Rotina original preservada.')
            put(DATA + '/config.json', json.dumps(config, ensure_ascii=False).encode(), 0o600)
        else:
            config = json.loads(cfgpath.read_text())
            if not isinstance(config, dict):
                raise RuntimeError('Configuração local inválida. Nenhuma substituição será feita.')
        if not target(DATA + '/schedule.json').exists():
            # Avoid a second automatic send on migration day.
            put(DATA + '/schedule.json', json.dumps({'date': datetime.date.today().isoformat()}).encode(), 0o600)
        put(SERVICE, (SOURCE / 'service/service.php').read_bytes())
        for name in ['index.php', 'app.css', 'app.js', 'manifest.json']:
            put(WEB + '/' + name, (SOURCE / 'addon' / name).read_bytes())
        # A tiny wrapper replaces a deployment-specific symlink.
        wrapper = target(WEB + '/addons.class.php')
        if wrapper.is_symlink():
            link = os.readlink(str(wrapper))
            wrapper.unlink()
            records.append((wrapper, ('symlink', link), None))
        put(WEB + '/addons.class.php', b"<?php require_once '/opt/mk-auth/include/addons.inc.hhvm';\n")
        sudo = 'www-data ALL=(root) NOPASSWD: /usr/bin/php ' + SERVICE + '\n'
        with tempfile.NamedTemporaryFile(mode='w', prefix='mka-sudo-', delete=False) as stream:
            stream.write(sudo)
            tmp = stream.name
        try:
            subprocess.run(['visudo', '-cf', tmp], check=True, stdout=subprocess.DEVNULL)
        finally:
            os.unlink(tmp)
        put('/etc/sudoers.d/mka-backup-telegram', sudo.encode(), 0o440)
        menu_path = target('/opt/mk-auth/admin/addons/addon.js')
        menu = menu_path.read_text()
        pattern = re.escape(MENU_BEGIN) + r'.*?' + re.escape(MENU_END)
        if MENU_BEGIN in menu and MENU_END not in menu:
            raise RuntimeError('Marcador de menu incompleto. Revise addon.js.')
        if re.search(pattern, menu, re.S):
            menu = re.sub(pattern, lambda _: MENU, menu, flags=re.S)
        else:
            menu = menu.rstrip() + '\n\n' + MENU + '\n'
        put('/opt/mk-auth/admin/addons/addon.js', menu.encode(), menu_path.stat().st_mode & 0o777)
        for line in old_lines:
            cron = cron.replace(line, '# Migrado para addon Backup Telegram: ' + line)
        put('/etc/crontab', cron.encode(), cronpath.stat().st_mode & 0o777)
        put('/etc/cron.d/mka-backup-telegram', ('SHELL=/bin/sh\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n* * * * * root /usr/bin/php '+SERVICE+' tick >/dev/null 2>&1\n').encode())
        manifest = [{'path': str(path.relative_to(prefix)), 'backup': previous.name if isinstance(previous, pathlib.Path) else previous, 'mode': mode} for path, previous, mode in records]
        (snapshot / 'rollback.json').write_text(json.dumps(manifest, indent=2))
        for old in sorted(backups.glob('install-*'), key=lambda item: item.stat().st_mtime, reverse=True)[5:]:
            if old.is_dir() and not old.is_symlink() and old.resolve().parent == backups.resolve():
                shutil.rmtree(str(old))
        print('Instalado: Provedor > Backup Telegram (v1.3.0).')
        print('Configuração local preservada. Nenhum envio de teste foi iniciado.')
        print('Retenção: 100 operações e 5 snapshots de instalação. Backups MK-AUTH não são removidos.')
    except BaseException:
        for path, previous, mode in reversed(records):
            if path.exists() or path.is_symlink():
                path.unlink()
            if isinstance(previous, tuple):
                path.symlink_to(previous[1])
            elif previous is not None:
                shutil.copy2(str(previous), str(path))
                os.chmod(str(path), mode)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Validar o pacote sem instalar')
    parser.add_argument('--root', default='/', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise RuntimeError('Execute como root.')
    verify()
    if args.check:
        print('Pacote e sintaxe PHP: OK. Nenhuma alteração realizada.')
        return
    prefix = pathlib.Path(args.root).resolve()
    if not prefix.is_dir():
        raise RuntimeError('Diretório de destino inexistente.')
    install(prefix)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('Instalação interrompida: ' + str(exc), file=sys.stderr)
        sys.exit(1)

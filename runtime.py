"""Configura comando fixo e confinamento do serviço sem trocar o PHP do sistema."""
import json
import pathlib
import re
import shutil
import subprocess
import tempfile


def configure_runtime(prefix, target, put):
    php = str(pathlib.Path(shutil.which('php')).resolve())
    if not re.match(r'^/[-./A-Za-z0-9_]+$', php):
        raise RuntimeError('Caminho do PHP não suportado.')
    service = '/usr/local/lib/mka-backup-telegram/service.php'
    command = [php, service]
    native_profiles = [target('/etc/apparmor.d/' + name) for name in ['sistema.php-admin', 'sistema.php-central']]
    apache_admin = target('/etc/apparmor.d/apache2.d/admin')
    apache_main = target('/etc/apparmor.d/usr.sbin.apache2')
    legacy_apache = apache_admin.is_file() and apache_main.is_file()
    enabled = target('/sys/module/apparmor/parameters/enabled')
    confined = enabled.is_file() and enabled.read_text().strip().upper() == 'Y' and (legacy_apache or any(p.is_file() for p in native_profiles))
    if confined:
        if not shutil.which('aa-exec') or not shutil.which('apparmor_parser'):
            raise RuntimeError('AppArmor ativo, mas faltam aa-exec ou apparmor_parser.')
        php_tree = str(pathlib.Path(php).parent.parent)
        profile = '''#include <tunables/global>
profile mka-backup-telegram flags=(attach_disconnected) {
 #include <abstractions/base>
 network inet,
 network inet6,
 network unix,
 signal,
 /etc/** r,
 /run/resolvconf/resolv.conf r,
 /usr/** mr,
 /lib/** mr,
 /lib64/** mr,
 PHP_TREE/** mr,
 PHP_EXEC ix,
 /bin/dash ix,
 /usr/bin/dash ix,
 /bin/sh ix,
 /usr/bin/sh ix,
 /usr/bin/timeout ix,
 /bin/bzip2 ix,
 /usr/bin/bzip2 ix,
 /proc/** r,
 /sys/kernel/mm/transparent_hugepage/hpage_pmd_size r,
 /dev/null rw,
 /dev/urandom r,
 /dev/random r,
 /opt/mk-auth/include/conexao.php r,
 /var/lib/mka-backup-telegram/ rw,
 /var/lib/mka-backup-telegram/** rwk,
 /opt/mk-auth/bckp/ r,
 /opt/mk-auth/bckp/* r,
}
'''.replace('PHP_TREE', php_tree).replace('PHP_EXEC', php)
        put('/etc/apparmor.d/mka-backup-telegram', profile.encode())
        put('/etc/apparmor.d/local/mka-backup-telegram-transition', b'change_profile -> mka-backup-telegram,\n')
        include = '#include if exists <local/mka-backup-telegram-transition>'
        for path in native_profiles:
            if not path.is_file():
                continue
            original = path.read_text()
            if include not in original:
                pos = original.rfind('}')
                if pos < 0:
                    raise RuntimeError('Perfil AppArmor nativo não reconhecido: ' + path.name)
                updated = original[:pos] + '  ' + include + '\n' + original[pos:]
                put('/etc/apparmor.d/' + path.name, updated.encode(), path.stat().st_mode & 0o777)
        if legacy_apache:
            # Legacy mod_apparmor executes admin PHP inside apache2//admin.
            # Only the fixed sudo command can transition into the private worker.
            put('/etc/apparmor.d/local/mka-backup-telegram-apache-admin', b'capability setuid,\ncapability setgid,\nchange_profile -> mka-backup-telegram,\n')
            original = apache_admin.read_text()
            admin_include = '#include if exists <local/mka-backup-telegram-apache-admin>'
            if admin_include not in original:
                pos = original.rfind('}')
                if pos < 0:
                    raise RuntimeError('Perfil administrativo do Apache nao reconhecido.')
                updated = original[:pos] + '  ' + admin_include + '\n' + original[pos:]
                put('/etc/apparmor.d/apache2.d/admin', updated.encode(), apache_admin.stat().st_mode & 0o777)
        profiles = [target('/etc/apparmor.d/mka-backup-telegram')] + [p for p in native_profiles if p.is_file()]
        if legacy_apache:
            profiles.append(apache_main)
        for path in profiles:
            subprocess.run(['apparmor_parser', '-Q', str(path)], check=True, stdout=subprocess.DEVNULL)
        if prefix == pathlib.Path('/'):
            for path in profiles:
                subprocess.run(['apparmor_parser', '-r', str(path)], check=True, stdout=subprocess.DEVNULL)
        command = ['/usr/bin/aa-exec', '-p', 'mka-backup-telegram', '--', php, '-d', 'opcache.enable_cli=0', '-d', 'pcre.jit=0', service]
    # Public runtime metadata contains only fixed command paths, never credentials.
    put('/usr/local/lib/mka-backup-telegram/command.json', json.dumps(command).encode())
    rule = 'www-data ALL=(root) NOPASSWD: ' + ' '.join(command) + '\n'
    # Keep a managed rule in the main file: some MK-AUTH jobs rebuild sudoers.d.
    sudoers = target('/etc/sudoers')
    if not sudoers.is_file():
        raise RuntimeError('/etc/sudoers não encontrado.')
    original = sudoers.read_text()
    begin, end = '# MKA-BACKUP-TELEGRAM-BEGIN', '# MKA-BACKUP-TELEGRAM-END'
    block = begin + '\n' + rule + end
    pattern = re.escape(begin) + r'.*?' + re.escape(end)
    if begin in original and end not in original:
        raise RuntimeError('Bloco do addon incompleto em /etc/sudoers.')
    updated = re.sub(pattern, lambda _: block, original, flags=re.S) if begin in original else original.rstrip() + '\n\n' + block + '\n'
    with tempfile.NamedTemporaryFile(mode='w') as candidate:
        candidate.write(updated)
        candidate.flush()
        subprocess.run(['visudo', '-cf', candidate.name], check=True, stdout=subprocess.DEVNULL)
    put('/etc/sudoers', updated.encode(), sudoers.stat().st_mode & 0o777)
    if target('/etc/sudoers.d/mka-backup-telegram').is_file():
        put('/etc/sudoers.d/mka-backup-telegram', rule.encode(), 0o440)
    return php

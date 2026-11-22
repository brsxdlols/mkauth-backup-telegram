"""Descobre um PHP CLI completo sem alterar PATH, symlinks ou alternatives."""
import glob
import json
import pathlib
import re
import shutil
import subprocess

PROBE = r'''echo json_encode([
 'sapi'=>PHP_SAPI,'version'=>PHP_VERSION,'id'=>PHP_VERSION_ID,
 'missing'=>array_values(array_filter(['curl','json','mysqli','posix'],function($m){return !extension_loaded($m);})),
 'functions'=>function_exists('proc_open')&&function_exists('flock')&&function_exists('random_bytes')
]);'''


def candidates():
    result = [shutil.which('php'), '/usr/local/bin/php', '/usr/bin/php', '/opt/php8/bin/php', '/opt/mk-auth/hhvm/bin/php']
    for pattern in ['/usr/bin/php[0-9]*', '/usr/local/bin/php[0-9]*', '/opt/php*/bin/php', '/opt/mk-auth/hhvm/*/bin/php']:
        result.extend(sorted(glob.glob(pattern)))
    return result


def select_php(paths=None):
    compatible, diagnostics, seen = [], [], set()
    for value in candidates() if paths is None else paths:
        if not value:
            continue
        path = pathlib.Path(value).resolve()
        name = str(path)
        if name in seen or not path.is_file():
            continue
        seen.add(name)
        if not re.match(r'^/[-./A-Za-z0-9_]+$', name):
            continue
        try:
            run = subprocess.run([name, '-r', PROBE], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=8)
            data = json.loads(run.stdout.decode('utf-8'))
            if run.returncode or data.get('sapi') != 'cli':
                diagnostics.append(name + ': não é um PHP CLI utilizável')
                continue
            version = int(data['id'])
            if not 70300 <= version < 90000:
                diagnostics.append(name + ': PHP ' + data['version'] + ' fora da faixa suportada (7.3–8.x)')
                continue
            if data.get('missing') or not data.get('functions'):
                diagnostics.append(name + ': faltam extensões ou funções: ' + ', '.join(data.get('missing', [])))
                continue
            compatible.append((version, name, data['version']))
        except (OSError, ValueError, subprocess.TimeoutExpired, KeyError):
            diagnostics.append(name + ': não respondeu à verificação')
    if not compatible:
        details = '\n'.join(diagnostics) or 'Nenhum executável PHP encontrado nos caminhos conhecidos.'
        raise RuntimeError('Nenhum PHP CLI compatível disponível. É necessário PHP 7.3–8.x com curl, json, mysqli e posix.\n' + details)
    # Deterministic preference for the newest complete installed runtime.
    version, name, label = sorted(compatible, key=lambda item: (-item[0], item[1]))[0]
    print('PHP selecionado automaticamente: ' + label + ' (' + name + ')', flush=True)
    print('PHP padrão do MK-AUTH mantido.', flush=True)
    return name

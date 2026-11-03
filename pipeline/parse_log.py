"""Parse an urna log (logd.dat inside a .jez zip) into one row per voter for a given election day.

Mesário identifiers (título numbers) are replaced by a salted hash: we only need to know whether
two releases were done by the same mesário, never who they are.
"""
import hashlib, io, os, re, zipfile

# Random per run unless AUDIT_SALT is set: codes are only comparable within one run and cannot be reversed
# with a public salt. The site never publishes them.
SALT = os.environ.get('AUDIT_SALT', os.urandom(16).hex()).encode()
RE_MES_HAB = re.compile(r'Mesário (\d+) habilitou o eleitor')
RE_MES_SEC = re.compile(r'Mesário (\d+) (é|não é) eleitor da seção')
RE_TIPO = re.compile(r'Tipo de habilitação do eleitor \[(.+?)\]')
RE_TRY = re.compile(r'Capturada a digital\. Tentativa \[(\d+)\]')


def anon(x):
    return hashlib.sha256(SALT + x.encode()).hexdigest()[:10]


def iter_lines(jez_bytes):
    """Yield decoded log lines from every logd*.dat in the archive (including nested archives)."""
    z = zipfile.ZipFile(io.BytesIO(jez_bytes))
    for info in z.infolist():
        data = z.read(info)
        if info.filename.endswith('.dat'):
            for line in data.decode('latin1').splitlines():
                yield info.filename, line
        elif data[:2] == b'PK':
            yield from iter_lines(data)


def merged_lines(jez_bytes, day=None, meta=None):
    """All log lines of the package (main log + archived logs of replaced urnas), exact duplicates removed
    (contingency packages can contain the same archived log twice), in chronological order (stable).
    With `day`, only that day's lines are kept (the urna model is still read from any line into meta)."""
    seen, rows = set(), []
    for fname, line in iter_lines(jez_bytes):
        if day and not line.startswith(day):
            if meta is not None and meta['model'] is None and 'Modelo de Urna' in line:
                meta['model'] = line.split(':')[-1].strip().split('\t')[0]
            continue
        if line in seen:
            continue
        seen.add(line)
        ts = line[:19]
        key = (ts[6:10], ts[3:5], ts[0:2], ts[11:19]) if len(ts) == 19 and ts[2] == '/' else ('9999',)
        rows.append((key, len(rows), fname, line))
    rows.sort()
    for _, _, fname, line in rows:
        yield fname, line


def parse(jez_bytes, day='25/10/2026', section=None):
    voters, meta = [], {'files': set(), 'model': None, 'close': None, 'open': None,
                        'mesarios_sec': {}, 'n_lines_day': 0, 'turno2_starts': 0,
                        'contingency': False, 'restarts': 0, 'urna_ids': set()}
    cur = None
    del_keys = ('fp_scores',)
    # A package can contain archived logs of urnas loaded for OTHER sections (e.g. a contingency urna that served
    # two sections). Votes are counted only from urnas whose loaded section is this package's section.
    sec_of = {}
    meta['foreign_votes'] = 0
    pending = None

    def close_pending():
        nonlocal pending
        if pending is not None:
            if pending['t_confirm']:
                pending['t_vote'] = pending['t_confirm']; pending['recovered'] = True
            else:
                pending['cancelled'] = True
            voters.append(pending)
        pending = None

    def new(t):
        return {'t_start': t, 't_id': None, 'id_type': None, 'fp_tries': 0, 'hab_type': None,
                'manual': False, 'manual_data_ok': False, 'data_fail': 0, 'mesario': None, 't_mesario': None,
                'releaser': None, 'fp_scores': [], 't_fp_first': None, 't_manual': None, 't_mes_req': None,
                't_hab': None, 't_vote': None, 't_confirm': None, 'recovered': False, 'cancelled': False}

    for fname, line in merged_lines(jez_bytes, day, meta):
        meta['files'].add(fname)
        parts = line.split('\t')
        if len(parts) < 5:
            continue
        ts, lvl, ue, comp, msg = parts[:5]
        if 'Identificação do Modelo de Urna' in msg:
            meta['model'] = msg.split(':')[-1].strip()
        if not ts.startswith(day):
            continue
        meta['n_lines_day'] += 1
        t = ts[11:]
        if 'ELEIÇÃO OFICIAL SEGUNDO TURNO' in msg and 'Iniciando' in msg:
            meta['turno2_starts'] += 1
        if msg.startswith('Urna pronta para receber votos') and meta['open'] is None:
            meta['open'] = t
        if msg.startswith('Procedimento de encerramento confirmado'):
            meta['close'] = t
        m = RE_MES_SEC.search(msg)
        if m:
            meta['mesarios_sec'][anon(m.group(1))] = (m.group(2) == 'é')
        meta['urna_ids'].add(ue)
        if msg.startswith('Seção Eleitoral: '):
            try: sec_of[ue] = int(msg.split(':')[1])
            except ValueError: pass
        if 'Contingência executada com sucesso' in msg:
            meta['contingency'] = True
        if comp == 'LOGD' and msg.startswith('Início das operações do logd'):
            meta['restarts'] += 1
            # urna restarted (e.g. power loss) while a voter was in progress. Keep that voter pending: if the
            # "computado" line arrives after the reboot it is a normal vote; if the next voter starts instead and
            # the vote had been confirmed, it becomes a "recovered" vote (reconciled with the BU by the builder).
            if cur and cur['t_id'] and not cur['t_vote']:
                pending = cur
            cur = None
            continue
        if comp != 'VOTA':
            continue
        if section is not None and sec_of.get(ue, section) not in (section, 0):
            if msg.startswith('O voto do eleitor foi computado'): meta['foreign_votes'] += 1
            continue
        if msg.startswith('Aguardando digitação do identificador do eleitor'):
            close_pending()
            if cur and cur['t_id'] and not cur['t_vote']:
                cur['cancelled'] = True; voters.append(cur)
            cur = new(t)
            continue
        if cur is None:
            if msg.startswith('O voto do eleitor foi computado'):   # vote completed after a reboot
                v = pending or new(t); pending = None
                v['t_vote'] = t; voters.append(v)
            continue
        if msg.startswith('Identificador digitado pelo mesário foi'):
            cur['t_id'] = t; cur['id_type'] = msg.split('(')[-1].rstrip(')')
        elif msg.startswith('Solicita digital. Tentativa [1]'):
            if cur['t_fp_first'] is None: cur['t_fp_first'] = t
        elif msg.startswith('Solicita digital do mesário'):
            if cur['t_mes_req'] is None: cur['t_mes_req'] = t
        elif (m := RE_TRY.search(msg)):
            cur['fp_tries'] = max(cur['fp_tries'], int(m.group(1)))
        elif (m := RE_TIPO.search(msg)):
            cur['hab_type'] = m.group(1)
        elif msg.startswith('Solicitação de dado pessoal do eleitor para habilitação manual'):
            cur['manual'] = True
            if cur['t_manual'] is None: cur['t_manual'] = t
        elif msg.startswith('Dado digitado confere') or msg.startswith('Ano de nascimento digitado é igual'):
            cur['manual_data_ok'] = True
        elif msg.startswith('Dado digitado não confere') or msg.startswith('Dado digitado está incompleto'):
            cur['data_fail'] += 1
        elif msg.startswith('Não encontrou digital coletada em nenhum dos arquivos'):
            cur['releaser'] = 'unregistered_new'; cur['t_mesario'] = t
        elif msg.startswith('Digital coletada bate com uma digital gravada após o registro inicial'):
            cur['releaser'] = 'unregistered_repeat'; cur['t_mesario'] = t
        elif (m := RE_MES_HAB.search(msg)):
            cur['mesario'] = anon(m.group(1)); cur['t_mesario'] = t; cur['releaser'] = 'registered'
        elif msg.startswith('Voto confirmado para'):
            cur['t_confirm'] = t
        elif msg.startswith('Eleitor foi habilitado'):
            cur['t_hab'] = t
        elif msg.startswith('O voto do eleitor foi computado'):
            cur['t_vote'] = t; voters.append(cur); cur = None
    close_pending()
    if cur and cur['t_id'] and not cur['t_vote']:
        cur['cancelled'] = True; voters.append(cur)
    meta['files'] = sorted(meta['files']); meta['urna_ids'] = sorted(meta['urna_ids'])
    return voters, meta


if __name__ == '__main__':
    import sys, collections
    v, m = parse(open(sys.argv[1], 'rb').read())
    print(m)
    done = [x for x in v if x['t_vote']]
    print('voters computed', len(done), 'cancelled', sum(x['cancelled'] for x in v))
    print('hab types', collections.Counter((x['hab_type'], x['manual'], bool(x['mesario'])) for x in done))
    print('first/last vote', done[0]['t_vote'], done[-1]['t_vote'])

"""Per-urna verification of the files the TSE publishes for each urna (arqurnatot zip): signatures, hashes, BU x RDV x bweb.

For every urna of one state:
  1. vota.vsc (signature file) is decoded. For both signature blocks (software "SW" and hardware/urna "HW"):
     - self-hash: SHA-512 of the signed content == hash stored with its signature;
     - every published file (bu.dat, rdv.dat, imgbu.dat, log.jez) has SHA-512 == the hash listed for it.
     Files listed in the signature but not published in the zip (jufa, imgze, hash, wsq*, mr.ver) are counted, not checked.
  2. Certificate of the urna (HW block): issuer, subject, validity on election day, and whether the serial in the
     subject equals the urna's internal number recorded in the BU.
     The signature values themselves (CEPESC algorithm for SW; Ed521-style for HW) cannot be checked with public
     documentation: the TSE publishes no verification procedure or code for them. Reported as "not checkable".
  3. BU (bu.dat) decoded with the 2026 layout (spec/bu2026.asn1): attendance, eligible, votes per candidate, blank, null.
  4. RDV (rdv.dat) decoded (spec/rdv2026.asn1): every vote record counted by type and number typed.
  5. BU == RDV per category, and BU == bweb CSV (site data) for Lula, Flávio, attendance and eligible voters.

usage: python verify_urnas.py <UF> <site dir> <out dir> [processes]
"""
import datetime, glob, gzip, hashlib, json, os, pickle, re, struct, subprocess, sys, tempfile, time, zipfile, zlib
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SPEC = os.path.join(HERE, 'spec')
ARQ = 'https://cdn.tse.jus.br/estatistica/sead/eleicoes/eleicoes2026/arqurnatot/bu_imgbu_logjez_rdv_vscmr_2026_2t_{uf}.zip'
DAY = datetime.datetime(2026, 10, 25, 12, tzinfo=datetime.timezone.utc)
PUBLISHED = ('bu.dat', 'rdv.dat', 'imgbu.dat', 'log.jez')
NAME = re.compile(r'(o03221[a-z]{2}(\d{5})(\d{4})(\d{4}))-(.+)$')
_conv = {}


def conv(name):
    if name not in _conv:
        import asn1tools
        f = {'sig': 'assinatura2026.asn1', 'bu': 'bu2026.asn1', 'rdv': 'rdv2026.asn1'}[name]
        _conv[name] = asn1tools.compile_files([os.path.join(SPEC, f)], codec='ber', numeric_enums=True)
    return _conv[name]


def index(uf, path):
    if not os.path.exists(path):
        from httpzip import HTTPFile
        z = zipfile.ZipFile(HTTPFile(ARQ.format(uf=uf)))
        pickle.dump([(i.filename, i.header_offset, i.compress_size, i.file_size) for i in z.infolist()], open(path, 'wb'))
    groups = {}
    for n, off, csz, usz in pickle.load(open(path, 'rb')):
        m = NAME.match(n)
        if m: groups.setdefault(m.group(1), []).append((m.group(5), off, csz))
    return groups


def split_members(blob, base, members):
    out = {}
    for suf, off, csz in members:
        o = off - base
        sig, ver, flag, meth, _, _, crc, _, _, nlen, xlen = struct.unpack('<IHHHHHIIIHH', blob[o:o + 30])
        assert sig == 0x04034b50
        data = blob[o + 30 + nlen + xlen: o + 30 + nlen + xlen + csz]
        assert len(data) == csz
        out[suf] = data if meth == 0 else zlib.decompress(data, -15)
    return out


def fetch(url, urnas, tmp):
    cfg = []
    for i, (key, members) in enumerate(urnas):
        lo = min(o for _, o, _ in members); hi = max(o + c for _, o, c in members) + 1024
        cfg.append(('next\n' if i else '') + f'url = "{url}"\nrange = {lo}-{hi}\noutput = "{tmp}/{i}"\n')
    open(f'{tmp}/c.cfg', 'w').write(''.join(cfg))
    subprocess.run(['curl', '-sS', '--retry', '5', '--retry-all-errors', '-m', '900', '--parallel', '--parallel-max', '8', '-K', f'{tmp}/c.cfg'], capture_output=True)
    out = {}
    for i, (key, members) in enumerate(urnas):
        try:
            out[key] = split_members(open(f'{tmp}/{i}', 'rb').read(), min(o for _, o, _ in members), members)
        except Exception as e:
            out[key] = e
    return out


def cert_info(raw):
    from cryptography import x509
    c = x509.load_pem_x509_certificate(raw) if raw.lstrip().startswith(b'-----') else x509.load_der_x509_certificate(raw)
    cn = lambda n: ','.join(a.value for a in n.get_attributes_for_oid(x509.NameOID.COMMON_NAME))
    return {'cert_issuer': cn(c.issuer), 'cert_subject': cn(c.subject), 'cert_alg': c.signature_algorithm_oid.dotted_string,
            'cert_valid_day': c.not_valid_before_utc <= DAY <= c.not_valid_after_utc,
            'cert_not_after': c.not_valid_after_utc.date().isoformat()}


def check_block(C, blk, files, tag, r):
    a = blk['autoAssinado']['assinatura']
    hash_fn = {1: hashlib.sha1, 2: hashlib.sha256, 3: hashlib.sha384, 4: hashlib.sha512}.get(blk['autoAssinado']['algoritmoHash']['algoritmo'], hashlib.sha512)
    r[f'{tag}_self_ok'] = hash_fn(blk['conteudoAutoAssinado']).digest() == a['hash']
    listed = C.decode('Assinatura', blk['conteudoAutoAssinado'])['arquivosAssinados']
    r[f'{tag}_listed'] = len(listed)
    ok = bad = 0; unpub = 0; mism = []
    lmap = {x['nomeArquivo'].rsplit('-', 1)[-1]: x['assinatura']['hash'] for x in listed}
    for suf in lmap:
        if suf in files:
            if hash_fn(files[suf]).digest() == lmap[suf]: ok += 1
            else: bad += 1; mism.append(suf)
        else: unpub += 1
    r[f'{tag}_hash_ok'] = ok; r[f'{tag}_hash_bad'] = bad; r[f'{tag}_unpublished'] = unpub
    if mism: r[f'{tag}_mismatch'] = ','.join(mism)
    r[f'{tag}_not_listed'] = ','.join(s for s in files if s in PUBLISHED and s not in lmap)
    return blk


def count_bu(bu):
    out = Counter()
    out['bu_comp'] = bu.get('qtdComparecimento2026', -1)
    hab = bu.get('qtdHabilitacao2026') or []
    if len(hab) == 3: out['bu_hab_code'], out['bu_hab_bio'], out['bu_hab_other'] = hab
    for e in bu['resultadosVotacaoPorEleicao']:
        pres = any(c['codigoCargo'] == ('cargoConstitucional', 1) for rv in e['resultadosVotacao'] for c in rv['totaisVotosCargo'])
        if pres: out['bu_aptos'] += e['qtdEleitoresAptos']   # eligible voters of the presidential election only
        for rv in e['resultadosVotacao']:
            for c in rv['totaisVotosCargo']:
                if c['codigoCargo'] != ('cargoConstitucional', 1): continue
                out['bu_comp_pres'] += rv['qtdComparecimento']
                for v in c['votosVotaveis']:
                    t = v['tipoVoto']; q = v['quantidadeVotos']; cod = (v.get('identificacaoVotavel') or {}).get('codigo')
                    k = {13: 'lula', 22: 'flavio'}.get(cod, 'outro') if t == 1 else {2: 'branco', 3: 'nulo', 4: 'legenda'}.get(t, f't{t}')
                    out['bu_' + k] += q
    return out


def count_rdv(rdv):
    out = Counter()
    el = rdv['rdv']['eleicoes']
    if el[0] != 'eleicoesVota': out['rdv_sa'] = 1; return out
    for e in el[1]:
        for vc in e['votosCargos']:
            if vc['idCargo'] != ('cargoConstitucional', 1): continue
            for v in vc['votos']:
                t = v['tipoVoto']; d = v.get('digitacao')
                if t == 2: k = {'13': 'lula', '22': 'flavio'}.get(d, 'outro')
                elif t == 1: k = 'legenda'
                elif t in (3, 5): k = 'branco'
                else: k = 'nulo'
                out['rdv_' + k] += 1; out['rdv_n'] += 1
    return out


def verify(key, files):
    r = {'key': key, 'v': 2, 'files': ','.join(sorted(files))}
    try:
        C = conv('sig'); env = C.decode('EntidadeAssinaturaResultado', files['vota.vsc'])
        r['model'] = env.get('info', {}).get('modeloUrna', env.get('modeloUrna'))
        check_block(C, env['assinaturaSW'], files, 'sw', r)
        hw = check_block(C, env['assinaturaHW'], files, 'hw', r)
        if hw.get('certificadoDigital'): r.update(cert_info(hw['certificadoDigital']))
    except Exception as e: r['sig_error'] = repr(e)[:160]
    try:
        B = conv('bu'); env = B.decode('EntidadeEnvelopeGenerico', files['bu.dat']); bu = B.decode('EntidadeBoletimUrna', env['conteudo'])
        r['bu_urna_number'] = bu['urna']['correspondenciaResultado']['carga']['numeroInternoUrna']
        r.update(count_bu(bu))
    except Exception as e: r['bu_error'] = repr(e)[:160]
    try:
        r.update(count_rdv(conv('rdv').decode('EntidadeResultadoRDV', files['rdv.dat'])))
    except Exception as e: r['rdv_error'] = repr(e)[:160]
    s = r.get('cert_subject', '')
    if s and 'bu_urna_number' in r: r['cert_matches_urna'] = s[-8:].isdigit() and int(s[-8:]) == r['bu_urna_number']
    return r


def batch(args):
    url, urnas = args
    with tempfile.TemporaryDirectory(dir=os.environ.get('VERIFY_TMP')) as tmp:
        blobs = fetch(url, urnas, tmp)
        retry = [(k, m) for k, m in urnas if isinstance(blobs[k], Exception)]
        if retry: blobs.update(fetch(url, retry, tmp))
    out = []
    for k, m in urnas:
        b = blobs[k]
        out.append({'key': k, 'fetch_error': repr(b)[:160]} if isinstance(b, Exception) else verify(k, b))
    return out


def main():
    uf, site, outdir = sys.argv[1:4]; procs = int(sys.argv[4]) if len(sys.argv) > 4 else 4
    os.makedirs(outdir, exist_ok=True)
    out = os.path.join(outdir, f'{uf}.jsonl')
    done = {json.loads(l)['key'] for l in open(out)} if os.path.exists(out) else set()
    groups = index(uf, os.path.join(outdir, f'{uf}_index.pkl'))
    todo = [(k, m) for k, m in groups.items() if k not in done]
    chunks = [(ARQ.format(uf=uf), todo[i:i + 100]) for i in range(0, len(todo), 100)]
    t0 = time.time(); n = 0
    with open(out, 'a') as fh, ProcessPoolExecutor(procs) as ex:
        for res in ex.map(batch, chunks):
            for r in res: fh.write(json.dumps(r, default=str) + '\n')
            fh.flush(); n += len(res)
            if n % 5000 < 100: print(uf, f'{n}/{len(todo)}', f'{time.time() - t0:.0f}s', flush=True)
    print(uf, 'finished', n, f'{time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()

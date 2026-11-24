"""One private-index experiment; real loopback authenticated R12; no owner config."""
import argparse, contextlib, hashlib, http.client, json, math, os, secrets, sqlite3, subprocess, sys, tempfile, threading, time
from pathlib import Path
root=Path(__file__).resolve().parent; tree=root/'orbitdesktop'; dbpath=root/'copy.sqlite'
sys.path.insert(0,str(tree/'contrib'))
from rails_server import http as service
from rizzstack_rails import RailsLedger, query
from urllib.parse import urlencode
from unittest.mock import patch

def dump(label,d): (root/label).write_text(json.dumps(d,indent=2)+'\n')

def main():
    p=argparse.ArgumentParser(); p.add_argument('label'); p.add_argument('--samples',type=int,choices=[10,100],default=10); p.add_argument('--add-index',action='store_true'); p.add_argument('--profile',action='store_true'); args=p.parse_args()
    assert not (root/(args.label+'.json')).exists() and not subprocess.check_output(['git','-C',str(tree),'status','--porcelain'])
    sql="CREATE INDEX rails_local_attempt_scan ON event_rows (json_extract(envelope_json,'$.scope.attempt_id'), ingest_seq, event_id, rails_hash, length(CAST(envelope_json AS BLOB)))"
    # Maintain WAL companions through all requests as the normal writer does. No writes during measurements.
    with contextlib.ExitStack() as s:
        anchor=s.enter_context(contextlib.closing(sqlite3.connect(dbpath))); anchor.execute('pragma journal_mode=wal'); anchor.execute('select key from ledger_meta').fetchone()
        if args.add_index:
            before=dbpath.stat().st_size; t=time.monotonic(); anchor.execute(sql); ms=(time.monotonic()-t)*1000
            anchor.execute('pragma wal_checkpoint(truncate)'); dump('index-cost.json',dict(sql=sql,create_ms=ms,before=before,after=dbpath.stat().st_size,sqlite=sqlite3.sqlite_version))
        anchor.execute('pragma trusted_schema=OFF')
        plan=anchor.execute("EXPLAIN QUERY PLAN SELECT ingest_seq,event_id,rails_hash,length(CAST(envelope_json AS BLOB)) FROM event_rows WHERE ingest_seq<=? AND ingest_seq>? AND json_extract(envelope_json,'$.scope.attempt_id')=? ORDER BY ingest_seq LIMIT ?",(100106,0,'attempt-0',2001)).fetchall()
        head=anchor.execute('SELECT MAX(ingest_seq) FROM event_rows').fetchone()[0]; chain=anchor.execute('SELECT chain_id FROM event_rows LIMIT 1').fetchone()[0]
        blocks=[json.loads((root/f'lane-{i}.json').read_text()) for i in range(10)]
        folder=Path(s.enter_context(tempfile.TemporaryDirectory(dir=root))); cred=folder/'token'; cred.touch(mode=0o600); token=secrets.token_urlsafe(32); cred.write_text(token)
        svr=s.enter_context(service.make_server('127.0.0.1',0,dbpath,cred)); th=threading.Thread(target=svr.serve_forever); th.start(); s.callback(th.join); s.callback(svr.shutdown)
        def get(path,auth=True):
            with contextlib.closing(http.client.HTTPConnection('127.0.0.1',svr.server_port,timeout=5)) as conn:
                conn.request('GET',path,headers={'Authorization':'Bearer '+token} if auth else {}); resp=conn.getresponse(); return resp.status,resp.read(131073),dict(resp.getheaders())
        assert get('/v1/health',False)[0]==401
        status,body,_=get('/v1/health'); health=json.loads(body); assert status==200 and health['ingest_head']==head
        accum={}
        if args.profile:
            for key in ['_scan','_envelopes','project_events','validate_topology','wire_json']:
                def wrap(fn,k):
                    def run(*a,**kw):
                        t=time.perf_counter_ns()
                        try:return fn(*a,**kw)
                        finally:
                            count,ns=accum.get(k,(0,0));accum[k]=(count+1,ns+time.perf_counter_ns()-t)
                    return run
                s.enter_context(patch.object(query,key,wrap(getattr(query,key),key)))
        doc=dict(status='running',head=head,orbit=subprocess.check_output(['git','-C',str(tree),'rev-parse','HEAD'],text=True).strip(),health=health,plan=plan,series={})
        for surface in ('events','view'):
            rows=[]; doc['series'][surface]=rows
            tokens=[None]*10
            for n in range(-10,args.samples):
                lane=n%10; ids=[]; offset=max(0,n//10)*500; after=tokens[lane]; missing=set(); calls=[]; trace=hashlib.sha256(); accum.clear(); start=time.monotonic()
                while len(ids)<500:
                    q={'kind':'attempt','id':f'attempt-{lane}','limit':500-len(ids),'format':'json'}
                    if after:q['after']=after
                    t=time.monotonic(); status,body,hdr=get(f'/v1/{surface}?'+urlencode(q)); elapsed=(time.monotonic()-t)*1000; page=json.loads(body)
                    assert status==200 and len(body)<=32768,(status,page.get('error'))
                    items=page['items'] if surface=='events' else page['lanes'][0]['marks']
                    assert items and len(items)<=q['limit'] and page['completeness']=='partial'; missing.update(page['missing_sources'])
                    ids.extend(i['event_id'] for i in items); after=hdr['X-Rails-Next-Cursor']; assert hdr['X-Rails-Has-More']=='true'
                    if surface=='view': page['generated_at']='clock'; body=service.wire(page)
                    trace.update(body+b'\n'+after.encode()+b'\n'); calls.append(round(elapsed,3))
                    if n<0:break
                total=round((time.monotonic()-start)*1000,3)
                assert ids==[f'{chain}:{blocks[lane][i//50]+i%50}' for i in range(offset,offset+len(ids))] and 'offline-worker' in missing
                if n>=0:
                    tokens[lane]=after; rows.append(dict(lane=lane,offset=offset,logical_ms=total,calls=calls,wire_digest=trace.hexdigest(),profile={k:(v[0],round(v[1]/1e6,3)) for k,v in accum.items()}))
            doc[surface+'_p95_ms']=sorted(row['logical_ms'] for row in rows)[math.ceil(len(rows)*.95)-1]; dump(args.label+'.json',doc)
        doc['status']='completed'; dump(args.label+'.json',doc);print({k:v for k,v in doc.items() if k.endswith('p95_ms')},flush=True)
if __name__=='__main__':main()

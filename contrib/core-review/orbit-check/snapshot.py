"""Export working source and only the Git objects needed by the ordinary suite."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

repo, manifest, dest = map(Path, sys.argv[1:])
git_env = {'PATH':'/usr/bin:/bin', 'HOME':'/nonexistent', 'GIT_CONFIG_NOSYSTEM':'1',
           'GIT_CONFIG_GLOBAL':'/dev/null', 'GIT_ALLOW_PROTOCOL':'', 'GIT_NO_LAZY_FETCH':'1',
           'GIT_NO_REPLACE_OBJECTS':'1', 'GIT_OPTIONAL_LOCKS':'0', 'LC_ALL':'C'}

def git(*args, cwd=repo, data=None):
    return subprocess.check_output(['/usr/bin/git', '-c','core.hooksPath=/dev/null',
        '-c','core.fsmonitor=false', '-C',str(cwd),*args],env=git_env,input=data)

def safe(name):
    p = PurePosixPath(name)
    bad = {'..','.git','.runtime','node_modules','__pycache__','.ssh','.npmrc','.git-credentials',
           'dist','transcripts','screenshots','credentials','secrets','.sites-runtime'}
    if (not name or str(p) != name or p.is_absolute() or any(ord(c)<32 for c in name)
        or any(x.lower() in bad or x.lower().startswith('.env') for x in p.parts)
        or p.suffix.lower() in {'.pem','.key','.pfx','.p12','.db','.sqlite','.sqlite3','.log'}):
        raise SystemExit('private or unsupported snapshot path; review required: '+repr(name))

def extra(name):
    safe(name)
    if name in {'scripts/worker-join/.gitattributes','contrib/rizzstack_rails/LICENSE'}: return True
    p = PurePosixPath(name)
    return (len(p.parts)>1 and p.parts[0] in {'src','server','scripts','tests','apps','packages','pc-launcher',
        'contracts','contrib','docs','deploy','public','config','extensions','examples','skills','plugin-catalog'}
        and not any(x.startswith('.') for x in p.parts)
        and p.suffix.lower() in {'.md','.py','.mjs','.cjs','.js','.tsx','.ts','.css','.html','.json','.yml','.yaml','.service','.sh'})

def records(data):
    return [s.decode() for s in data.split(b'\0') if s]

indexed = {}
for line in records(git('ls-files','--stage','-z')):
    spec, name = line.split('\t',1)
    mode, blob, stage = spec.split()
    safe(name)
    if mode not in {'100644','100755'} or stage!='0':
        raise SystemExit('unmerged, link or unsupported index entry: '+name)
    indexed[name] = blob
extras=set()
for line in manifest.read_text().splitlines():
    if not line or line.startswith('#'): continue
    if not extra(line) or line in extras: raise SystemExit('invalid or duplicate reviewed path: '+line)
    extras.add(line)
untracked=set(records(git('ls-files','-o','--exclude-standard','-z')))
unknown=extras - untracked - indexed.keys()
if unknown: raise SystemExit('missing/ignored reviewed paths: '+', '.join(sorted(unknown)))
# Report new source candidates rather than claiming to have checked a complete buildout.
unlisted=[]
for name in sorted(untracked-extras):
    try: eligible=extra(name)
    except SystemExit: eligible=False
    if eligible: unlisted.append(name)
if unlisted: raise SystemExit('review new untracked source paths and add to the manifest:\n'+'\n'.join(unlisted))

dest.mkdir(mode=0o700)
git('init','--quiet','--template=','-b','main',cwd=dest)
head=git('rev-parse','--verify','HEAD^{commit}').decode().strip()
# Full trees only for git archive fixtures and current HEAD. Other pinned reads use exact blobs.
trees={head:None,'a15d7eb947d0c5936ce7ac66b5cda0ce49b5fea3':None,
       'ae14c4f327765dc5ff8786070dedc9eb7e9b3abe':None,'d35142f812619c1a2492f0223fce2798cf105b6d':None,
       'b404cf13e4a5a6aef197f7d12394648672061da2':None,  # schema11-store archives this entire tree
       '5b31fdaba1f867eeaf7b0aa30438f096a55b54f6':{'server/agent-profiles.mjs','tests/agent-profiles.test.mjs'},
       '6db86bdfe032e8417fdc719592f9bb89d5f4272d':{'server/workbench-environments.mjs'}}
objects=set(indexed.values())
for rev, files in trees.items():
    objects.update([rev,git('rev-parse',rev+'^{tree}').decode().strip()])
    for line in records(git('ls-tree','-rtz',rev)):
        spec,name=line.split('\t',1); mode,kind,obj=spec.split()
        if files is None or name in files or (kind=='tree' and any(p.startswith(name+'/') for p in files)):
            safe(name); objects.add(obj)
pack=git('pack-objects','--no-reuse-delta','--stdout',data=('\n'.join(sorted(objects))+'\n').encode())
git('index-pack','--stdin',cwd=dest,data=pack)
git('update-ref','refs/heads/main',head,cwd=dest)
git('update-index','-z','--index-info',cwd=dest,data=git('ls-files','--stage','-z'))

def copy_file(name):
    fd=os.open(repo,os.O_DIRECTORY)
    try:
        parts=name.split('/')
        for part in parts[:-1]:
            nxt=os.open(part,os.O_NOFOLLOW|os.O_DIRECTORY,dir_fd=fd); os.close(fd); fd=nxt
        flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
        src=os.open(parts[-1],flags,dir_fd=fd)
    finally: os.close(fd)
    with os.fdopen(src,'rb') as f:
        st=os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1: raise SystemExit('nonregular or linked source: '+name)
        out=dest/name; out.parent.mkdir(parents=True,exist_ok=True)
        with out.open('xb') as w: shutil.copyfileobj(f,w)
        if os.fstat(f.fileno()).st_ctime_ns!=st.st_ctime_ns: raise SystemExit('source changed during copy: '+name)
        out.chmod(0o755 if st.st_mode&0o111 else 0o644)
    return hashlib.sha256(out.read_bytes()).hexdigest()

seen={}
for name in sorted(indexed.keys()|extras):
    try: seen[name]=copy_file(name)
    except FileNotFoundError:
        if name not in indexed: raise
        seen[name]=None  # Preserve a tracked worktree deletion.
print('HEAD:',head,'source paths:',len(seen),'reviewed untracked:',len(extras & untracked))
(dest.parent/'snapshot.json').write_text(json.dumps(dict(head=head,untracked=sorted(extras & untracked),files=seen),indent=2)+'\n')

#!/bin/sh
# Resume the verified installed release after authorized upstream Samba recovery.
# No package installation, download or additional controlled paid request.
set -eu
umask 027
[ "$(id -u)" -eq 0 ] && [ "$(hostname)" = CT112 ]
revision=34ac27e6e4d055b2b82afadbc6ababa92f042ce3
protected=/opt/dog-art/staging/$revision
release=/opt/dog-art/releases/0.1.0-$revision
python3 -I - <<'GUARD'
import hashlib,os,stat,subprocess,zipfile
from pathlib import Path
rev='34ac27e6e4d055b2b82afadbc6ababa92f042ce3'
release=Path('/opt/dog-art/releases/0.1.0-'+rev)
stage=Path('/opt/dog-art/staging')/rev
for p in (stage,release,Path('/etc/dog-art'),Path('/var/lib/dog-art'),Path('/var/lib/dog-art/acceptance'),Path('/etc/systemd/system/dog-art.service.d')):
 for q in (p,*p.parents):
  assert not q.is_symlink()
  if q.exists():assert q.is_dir()
 for q in (p,):
  if q.exists() and not str(q).startswith('/var/lib/dog-art'):
   assert q.stat().st_uid==0 and not q.stat().st_mode&0o022
assert hashlib.sha256((stage/'input.tar.gz').read_bytes()).hexdigest()=='38e41ec37e6631cdf2459d5b2d3e77fd2c6e4d4fc1f9bae3d683bb895804f2e8'
for p in (stage/'SOURCE_REVISION',release/'SOURCE_REVISION'):
 assert p.read_text().strip()==rev
assert Path('/opt/dog-art/current').resolve()==release
assert (stage/'scripts/verify-installed.py').read_bytes()==(release/'verify-installed.py').read_bytes()
for name in ('dog-art.service','dog-art-reset.service','dog-art-reset.timer'):
 expected=(stage/'deploy/systemd'/name).read_text().replace('/opt/dog-art/current',str(release))
 assert Path('/etc/systemd/system',name).read_text()==expected
 assert (release/'systemd'/name).read_text()==expected
assert subprocess.check_output(['systemctl','show','dog-art.service','-p','WorkingDirectory','--value'],text=True).strip()=='/var/lib/dog-art'
assert str(release/'venv/bin/dog-art') in subprocess.check_output(['systemctl','show','dog-art.service','-p','ExecStart','--value'],text=True)
for p in (Path('/etc/dog-art/app.toml'),Path('/etc/dog-art/.env'),release/'verify-installed.py'):
 assert p.is_file() and not p.is_symlink() and p.stat().st_uid==0 and not p.stat().st_mode&0o022
assert not Path('/etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf').exists()
assert not Path('/var/lib/dog-art/acceptance/operations-resume-'+rev).exists()
assert not Path('/etc/dog-art/app.toml.pre-live-resume-'+rev).exists()
# Exact app files come from the pinned wheel, independent of Python bytecode caches.
wheel=stage/'wheel/dog_art_pipeline-0.1.0-py3-none-any.whl'
assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='adc771122f342ee1c782efd432c9a00674c35d5f4f5eb7a9b83278181cf1bb40'
site=release/'venv/lib/python3.11/site-packages'
with zipfile.ZipFile(wheel) as z:
 for name in z.namelist():
  if name.startswith('dog_art/') and not name.endswith('/'):
   p=site/name
   assert p.is_file() and not p.is_symlink() and p.stat().st_uid==0 and not p.stat().st_mode&0o022
   assert p.read_bytes()==z.read(name)
print('Exact installed 34ac27e app, helper and units verified; no installation needed.')
GUARD
(cd "$protected" && sha256sum -c SHA256SUMS >/dev/null)
cd /
backup=/etc/dog-art/app.toml.pre-live-resume-$revision
promoting=0
acceptance_step=preparation
restore() {
 result=$?
 trap - EXIT HUP INT TERM
 if [ "$result" -ne 0 ]; then
  echo "Installed acceptance failed during $acceptance_step; preserving catalogs/artwork/receipts and restoring shadow mode." >&2
  journalctl -u dog-art-reset.service -u dog-art.service -n 40 --no-pager -o cat >&2 || true
  systemctl stop dog-art.service || true
  checkpoint=/var/lib/dog-art/acceptance/operations-resume-$revision
  if [ -f "$checkpoint/display-checkpoint.json" ]; then
   runuser -u dog-art -- "$release/venv/bin/python" -I "$release/verify-installed.py" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env --sandbox "$checkpoint" --restore-only || echo "Owned display restoration BLOCKED; preserve $checkpoint/display-checkpoint.json and rerun the same --restore-only command after SMB recovery." >&2
  fi
  if [ "$promoting" -eq 1 ]; then
   install -o root -g dog-art -m 0640 "$backup" /etc/dog-art/app.toml
   rm -f /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf
   systemctl daemon-reload || true
  fi
 fi
 systemctl start dog-art.service dog-art-reset.timer || true
 exit "$result"
}
trap restore EXIT
trap 'exit 130' HUP INT TERM
systemctl stop dog-art.service dog-art-reset.timer
portrait=$(runuser -u dog-art -- "$release/venv/bin/python" -I - <<'PORTRAIT'
from pathlib import Path
from dog_art.settings import load_settings
from dog_art.storage import Store
s=load_settings(Path('/etc/dog-art/app.toml'),Path('/etc/dog-art/.env'))
assert not s['OPENAI_GENERATION_ENABLED'] and not s['PUBLISH_ENABLED']
store=Store(Path(s['APP_DATA_ROOT'])/'catalog.sqlite')
try:
 rows=store.db.execute("SELECT path FROM portraits WHERE sha256=? AND state IN ('needs_review','validated')",('0cad9b03b90c1e9a9260d18f1d15d02dfcb3e495046c5319eaf07d8160c572dd',)).fetchall()
 assert len(rows)==1
 print(rows[0]['path'])
finally:store.close()
PORTRAIT
)
acceptance_step=hardened-helper
# Actual installed code under the production sandbox properties, isolated catalog.
systemd-run --quiet --wait --pipe --collect --unit "dog-art-resume-34ac27e" \
 --property=User=dog-art --property=Group=dog-art --property=UMask=0077 \
 --property=NoNewPrivileges=yes --property=PrivateTmp=yes \
 --property=ProtectSystem=strict --property=ProtectHome=yes \
 --property=ReadWritePaths=/var/lib/dog-art \
 --property='RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' \
 --property=MemoryMax=900M --property=CPUQuota=80% --property=RuntimeMaxSec=300 \
 "$release/venv/bin/python" -I "$release/verify-installed.py" \
 --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env \
 --sandbox "/var/lib/dog-art/acceptance/operations-resume-$revision" \
 --portrait "$portrait" --portrait-sha256 0cad9b03b90c1e9a9260d18f1d15d02dfcb3e495046c5319eaf07d8160c572dd \
 --baseline-day 2026-10-22 --baseline-sha256 b563c587bb7ca69ce9e125b3eb3d6f9b3249d236cce2a6b8d7985990103a8a2a
# Allow the real reset action to publish, with paid generation still disabled.
[ ! -e "$backup" ] && [ ! -L "$backup" ]
install -o root -g root -m 0600 /etc/dog-art/app.toml "$backup"
promoting=1
python3 -I - <<'RESET_POLICY'
import grp,os,re,tomllib
from pathlib import Path
p=Path('/etc/dog-art/app.toml');assert not p.is_symlink()
text=p.read_text();old=tomllib.loads(text)
assert not old['OPENAI_GENERATION_ENABLED'] and not old['PUBLISH_ENABLED']
text,count=re.subn(r'^PUBLISH_ENABLED\s*=.*$', 'PUBLISH_ENABLED = true',text,flags=re.M)
assert count==1 and tomllib.loads(text)=={**old,'PUBLISH_ENABLED':True}
tmp=p.with_name('.app-reset-34ac27e.tmp')
with tmp.open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
os.chown(tmp,0,grp.getgrnam('dog-art').gr_gid);tmp.chmod(0o640);tmp.replace(p)
RESET_POLICY
acceptance_step=installed-reset-action
# Actual installed reset unit is exercised without altering the wall clock.
systemctl start dog-art-reset.service
[ "$(systemctl show dog-art-reset.service -p Result --value)" = success ]
acceptance_step=accept-reviewed-bytes
# Accept only the one already human-reviewed output; no generation/API call here.
runuser -u dog-art -- "$release/venv/bin/python" -I - <<'ACCEPT'
from pathlib import Path
from dog_art.clock import Clock
from dog_art.portraits import PortraitService
from dog_art.settings import load_settings
from dog_art.storage import Store
s=load_settings(Path('/etc/dog-art/app.toml'),Path('/etc/dog-art/.env'))
store=Store(Path(s['APP_DATA_ROOT'])/'catalog.sqlite')
try:
 svc=PortraitService(store,s,Clock());svc.recover_saved()
 rows=store.db.execute('SELECT recipe_key FROM portraits WHERE sha256=?',('0cad9b03b90c1e9a9260d18f1d15d02dfcb3e495046c5319eaf07d8160c572dd',)).fetchall()
 assert len(rows)==1
 svc.accept(rows[0]['recipe_key'],reviewer='primary and independent actual visual review',evidence='docs/evidence/LIVE_PORTRAIT_AND_DISPLAY.md; exact saved SHA256; anatomy/style/cream-dark/confirmed black coat and white lower legs; authorized partial-policy unseen details interpretation')
 print('Already reviewed saved portrait accepted; no paid request.')
finally:store.close()
ACCEPT
acceptance_step=two-shadow-restarts
# Two real shadow restarts verify persistent startup recovery before ongoing mode.
for attempt in 1 2; do
 systemctl restart dog-art.service
 sleep 3
 systemctl is-active --quiet dog-art.service
 [ "$(systemctl show dog-art.service -p User --value)" = dog-art ]
 [ "$(systemctl show dog-art.service -p NRestarts --value)" = 0 ]
done
systemctl stop dog-art.service
acceptance_step=ongoing-live-promotion
python3 -I - <<'POLICY'
import grp,os,re,tomllib
from pathlib import Path
p=Path('/etc/dog-art/app.toml');assert not p.is_symlink()
text=p.read_text();old=tomllib.loads(text)
assert old['IDENTITY_MODE']=='per_observation' and old['SOURCE_REFERENCE_POLICY']=='best_effort_partial'
assert old['OPENAI_DAILY_BUDGET_USD']==5 and old['OPENAI_MAX_CALLS_PER_DAY']==12
assert old['OLLAMA_MODEL']=='qwen3-vl:8b'
assert old['OLLAMA_MODEL_DIGEST']=='9cf69da2b16d097f7def535917c4b55a95d6c7ee5700eb69ab86b01b3cfca487'
assert not old['OPENAI_GENERATION_ENABLED'] and old['PUBLISH_ENABLED']
changes={'OPENAI_GENERATION_ENABLED':True,'PUBLISH_ENABLED':True,'PORTRAIT_REVIEW_MODE':'local_vlm','OPENAI_PORTRAIT_RESERVATION_USD':0.5}
import json
for key,value in changes.items():
 line=key+' = '+json.dumps(value)
 if key in old:
  text,count=re.subn(r'^'+key+r'\s*=.*$',line,text,flags=re.M);assert count==1
 else:text+='\n'+line+'\n'
assert tomllib.loads(text)=={**old,**changes}
tmp=p.with_name('.app-live-34ac27e.tmp')
with tmp.open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
os.chown(tmp,0,grp.getgrnam('dog-art').gr_gid);tmp.chmod(0o640);tmp.replace(p)
POLICY
install -d -o root -g root -m 0755 /etc/systemd/system/dog-art.service.d
printf '[Service]\nEnvironment=DOG_ART_MODE=live\n' > /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf
chmod 0644 /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf
systemctl daemon-reload
systemctl start dog-art.service dog-art-reset.timer
sleep 3
systemctl is-active --quiet dog-art.service
systemctl is-active --quiet dog-art-reset.timer
runuser -u dog-art -- "$release/venv/bin/dog-art" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env status --redact
systemctl show dog-art.service -p User -p MainPID -p ActiveState -p SubState -p NRestarts
systemctl list-timers dog-art-reset.timer --no-pager
acceptance_step=bounded-live-observation
printf '%s\n' 'Observing ongoing live worker for 120 seconds; paid work follows the existing daily limits.'
for sample in 1 2 3 4 5 6 7 8; do
 sleep 15
 systemctl is-active --quiet dog-art.service
 [ "$(systemctl show dog-art.service -p NRestarts --value)" = 0 ]
 case "$sample" in 2|4|6|8)
  runuser -u dog-art -- "$release/venv/bin/dog-art" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env status --redact;;
 esac
done
# Aggregate-only operational evidence: no source images, descriptions or secrets.
runuser -u dog-art -- "$release/venv/bin/python" -I - <<'OBSERVATION'
import json
from pathlib import Path
from dog_art.clock import Clock
from dog_art.settings import load_settings
from dog_art.storage import Store
s=load_settings(Path('/etc/dog-art/app.toml'),Path('/etc/dog-art/.env'))
store=Store(Path(s['APP_DATA_ROOT'])/'catalog.sqlite')
try:
 day=Clock().day()
 report={'source_revision':'34ac27e6e4d055b2b82afadbc6ababa92f042ce3','ongoing_live_window_seconds':120,'status':store.status(),
 'generation_enabled':s['OPENAI_GENERATION_ENABLED'],'publication_enabled':s['PUBLISH_ENABLED'],
 'daily_usd':s['OPENAI_DAILY_BUDGET_USD'],'daily_calls':s['OPENAI_MAX_CALLS_PER_DAY'],
 'current_members':store.db.execute('SELECT count(*) FROM membership WHERE day=?',(day,)).fetchone()[0],
 'portrait_states':dict(store.db.execute('SELECT state,count(*) FROM portraits GROUP BY state').fetchall()),
 'outbox_states':dict(store.db.execute('SELECT state,count(*) FROM outbox WHERE day=? GROUP BY state',(day,)).fetchall())}
 last=store.db.execute('SELECT payload FROM publications ORDER BY created_at DESC LIMIT 1').fetchone()
 if last:
  p=json.loads(last[0]);report['last_publication']={k:p[k] for k in ('revision','sha256','state','verified_at')}
 print(json.dumps(report))
finally:store.close()
OBSERVATION
promoting=0
trap - EXIT HUP INT TERM
printf '%s\n' 'Installed checks passed. Ongoing live worker enabled under existing $5/day, 12-call/day limits; local QA holds failures and never retries paid generation. No additional controlled paid test was made. Native PTZ gate remains blocked; physical duplicate prevention remains deferred.'

#!/bin/sh
# Pinned application-only upgrade of the already live 34ac27e installation.
# Normal sudo authentication; no additional controlled paid request.
set -eu
umask 027
[ "$(id -u)" -eq 0 ] && [ "$(hostname)" = CT112 ]
revision=@REV@
previous=34ac27e6e4d055b2b82afadbc6ababa92f042ce3
release=/opt/dog-art/releases/0.1.0-$revision
prior=/opt/dog-art/releases/0.1.0-$previous
protected=/opt/dog-art/staging/$revision
archive=/home/chatgpt/dog-art-build/dog-art-delivery-0.1.0-@SHORT@.tar.gz
cd /
python3 -I - <<'GUARD'
import os,sqlite3,tomllib
from pathlib import Path
previous='34ac27e6e4d055b2b82afadbc6ababa92f042ce3'
prior=Path('/opt/dog-art/releases/0.1.0-'+previous)
for raw in ('/opt/dog-art/staging','/var/lib/dog-art/acceptance','/etc/dog-art','/etc/systemd/system/dog-art.service.d'):
 p=Path(raw)
 for q in (p,*p.parents):
  assert not q.is_symlink()
  if q.exists():assert q.is_dir()
assert Path('/opt/dog-art/current').resolve()==prior
assert (prior/'SOURCE_REVISION').read_text().strip()==previous
p=Path('/etc/dog-art/app.toml');assert not p.is_symlink()
s=tomllib.loads(p.read_text())
assert s['OPENAI_GENERATION_ENABLED'] and s['PUBLISH_ENABLED']
assert s['OPENAI_DAILY_BUDGET_USD']==5 and s['OPENAI_MAX_CALLS_PER_DAY']==12
assert s['IDENTITY_MODE']=='per_observation' and s['SOURCE_REFERENCE_POLICY']=='best_effort_partial'
mode=Path('/etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf')
assert mode.is_file() and not mode.is_symlink() and mode.stat().st_uid==0 and not mode.stat().st_mode&0o022
assert mode.read_text()=='[Service]\nEnvironment=DOG_ART_MODE=live\n'
assert not Path('/var/lib/dog-art/catalog.sqlite').is_symlink()
db=sqlite3.connect('file:/var/lib/dog-art/catalog.sqlite?mode=ro',uri=True)
assert db.execute("SELECT count(*) FROM requests WHERE state IN ('reserved','submitting','indeterminate')").fetchone()[0]==0,'Wait for active/uncertain paid request before upgrade'
db.close()
GUARD
[ ! -e "$release" ] && [ ! -L "$release" ]
[ ! -e "$protected" ] && [ ! -L "$protected" ]
[ -f "$archive" ] && [ ! -L "$archive" ]
install -d -o root -g root -m 0700 "$protected"
install -o root -g root -m 0600 "$archive" "$protected/input.tar.gz"
printf '%s\n' '@ARCHIVE_SHA@  '"$protected/input.tar.gz" | sha256sum -c -
tar --no-same-owner -xzf "$protected/input.tar.gz" -C "$protected"
(cd "$protected" && sha256sum -c SHA256SUMS)
# Preserve the current live configuration/mode and units before any service change.
install -d -o root -g root -m 0700 "$protected/before-units"
install -o root -g root -m 0600 /etc/dog-art/app.toml "$protected/app.toml.before"
install -o root -g root -m 0600 /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf "$protected/mode.before"
for unit in dog-art.service dog-art-reset.service dog-art-reset.timer; do
 install -o root -g root -m 0600 "/etc/systemd/system/$unit" "$protected/before-units/$unit"
done
step=quiesce
changed=0
restore() {
 result=$?
 trap - EXIT HUP INT TERM
 if [ "$result" -ne 0 ] && { [ "$changed" -eq 1 ] || [ -f "$protected/quiesce-started" ]; }; then
  echo "Approved-as-ready upgrade failed during $step; preserving all catalogs/artwork/receipts and restoring the prior live application." >&2
  journalctl -u dog-art-reset.service -u dog-art.service -n 35 --no-pager -o cat >&2 || true
  systemctl stop dog-art.service dog-art-reset.timer || true
  checkpoint=/var/lib/dog-art/acceptance/operations-ready-$revision
  # Only an interrupted controlled helper needs its dated baseline restored.
  # Preserve a later legitimately published current-day collage on other failures.
  if [ "$step" = hardened-helper ] && [ -f "$checkpoint/display-checkpoint.json" ]; then
   runuser -u dog-art -- "$release/venv/bin/python" -I "$release/verify-installed.py" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env --sandbox "$checkpoint" --restore-only || echo "Owned restoration blocked; preserve dated checkpoint and inspect SMB." >&2
  fi
  install -o root -g dog-art -m 0640 "$protected/app.toml.before" /etc/dog-art/app.toml
  install -o root -g root -m 0644 "$protected/mode.before" /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf
  for unit in dog-art.service dog-art-reset.service dog-art-reset.timer; do
   install -o root -g root -m 0644 "$protected/before-units/$unit" "/etc/systemd/system/$unit"
  done
  [ ! -e /opt/dog-art/.ready-rollback ] && [ ! -L /opt/dog-art/.ready-rollback ]
  ln -s "$prior" /opt/dog-art/.ready-rollback
  mv -Tf /opt/dog-art/.ready-rollback /opt/dog-art/current
  # A previous strict reader cannot reuse a ready-subset immutable revision.
  # Advance its desired counter, preserving every source, receipt and paid row.
  runuser -u dog-art -- "$prior/venv/bin/python" -I - <<'ROLLBACK_REVISION'
from pathlib import Path
from dog_art.storage import Store
s=Store(Path('/var/lib/dog-art/catalog.sqlite'))
try:
 with s.transaction() as db:
  day=db.execute("SELECT value FROM meta WHERE key='current_day'").fetchone()
  if day:
   db.execute('UPDATE days SET desired_revision=desired_revision+1 WHERE day=?',(day[0],))
   s.audit('approved_policy_upgrade_rollback',{'preserved_state':True},__import__('time').time(),db)
finally:s.close()
ROLLBACK_REVISION
  systemctl daemon-reload || true
  systemctl start dog-art.service dog-art-reset.timer || true
 fi
 exit "$result"
}
trap restore EXIT
trap 'exit 130' HUP INT TERM
# Do not interrupt a paid call. Quiesce while holding the application's existing
# paid barrier; a busy/indeterminate sender aborts before any service mutation.
"$prior/venv/bin/python" -I - <<'QUIESCE'
import sqlite3,subprocess
from pathlib import Path
from dog_art.daily import application_lock
from dog_art.safety import owned_path
root=Path('/var/lib/dog-art')
lock=owned_path(root,'locks/paid.lock')
assert lock.is_file()
catalog=owned_path(root,'catalog.sqlite')
with application_lock(lock,timeout=15):
 db=sqlite3.connect(catalog.as_uri()+'?mode=ro',uri=True)
 try:
  assert db.execute("SELECT count(*) FROM requests WHERE state IN ('reserved','submitting','indeterminate')").fetchone()[0]==0
 finally:db.close()
 Path('/opt/dog-art/staging/@REV@/quiesce-started').touch(exist_ok=False)
 subprocess.run(['systemctl','stop','dog-art.service','dog-art-reset.timer'],check=True,timeout=45)
QUIESCE
changed=1
# Block generation/publication during installation by using explicit shadow mode.
rm /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf
systemctl daemon-reload
step=install
/bin/sh "$protected/scripts/install-release.sh" "$protected" "$revision"
systemctl stop dog-art.service dog-art-reset.timer
install -o root -g dog-art -m 0640 "$protected/scripts/verify-installed.py" "$release/verify-installed.py"
step=policy
python3 -I - <<'POLICY'
import grp,os,re,tomllib
from pathlib import Path
p=Path('/etc/dog-art/app.toml');assert not p.is_symlink()
text=p.read_text();old=tomllib.loads(text)
assert old['OPENAI_GENERATION_ENABLED'] and old['PUBLISH_ENABLED']
key='COLLAGE_PORTRAIT_POLICY';line=key+' = "approved_only"'
if key in old:
 text,count=re.subn(r'^'+key+r'\s*=.*$',line,text,flags=re.M);assert count==1
else:text+='\n'+line+'\n'
assert tomllib.loads(text)=={**old,key:'approved_only'}
tmp=p.with_name('.app-ready-@SHORT@.tmp')
with tmp.open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
os.chown(tmp,0,grp.getgrnam('dog-art').gr_gid);tmp.chmod(0o640);tmp.replace(p)
POLICY
portrait=$(runuser -u dog-art -- "$release/venv/bin/python" -I - <<'PORTRAIT'
from pathlib import Path
from dog_art.storage import Store
s=Store(Path('/var/lib/dog-art/catalog.sqlite'))
try:
 rows=s.db.execute("SELECT path FROM portraits WHERE state='validated' AND sha256=?",('0cad9b03b90c1e9a9260d18f1d15d02dfcb3e495046c5319eaf07d8160c572dd',)).fetchall()
 assert len(rows)==1
 print(rows[0][0])
finally:s.close()
PORTRAIT
)
step=hardened-helper
systemd-run --quiet --wait --pipe --collect --unit "dog-art-ready-@SHORT@" \
 --property=User=dog-art --property=Group=dog-art --property=UMask=0077 \
 --property=WorkingDirectory=/var/lib/dog-art \
 --property=NoNewPrivileges=yes --property=PrivateTmp=yes \
 --property=ProtectSystem=strict --property=ProtectHome=yes \
 --property=ReadWritePaths=/var/lib/dog-art \
 --property='RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' \
 --property=MemoryMax=900M --property=CPUQuota=80% --property=RuntimeMaxSec=300 \
 "$release/venv/bin/python" -I "$release/verify-installed.py" \
 --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env \
 --sandbox "/var/lib/dog-art/acceptance/operations-ready-$revision" \
 --portrait "$portrait" --portrait-sha256 0cad9b03b90c1e9a9260d18f1d15d02dfcb3e495046c5319eaf07d8160c572dd \
 --baseline-day 2026-10-22 --baseline-sha256 6600c7a52f34193bdecba563976dffd2ff4f35ed67f083794d8d74868a209d53
step=installed-reset-and-ready-publication
systemctl start dog-art-reset.service
[ "$(systemctl show dog-art-reset.service -p Result --value)" = success ]
step=two-shadow-restarts
for attempt in 1 2; do
 systemctl restart dog-art.service
 sleep 3
 systemctl is-active --quiet dog-art.service
 [ "$(systemctl show dog-art.service -p NRestarts --value)" = 0 ]
done
systemctl stop dog-art.service
step=resume-live
install -o root -g root -m 0644 "$protected/mode.before" /etc/systemd/system/dog-art.service.d/10-dog-art-mode.conf
systemctl daemon-reload
systemctl start dog-art.service dog-art-reset.timer
step=observation
for sample in 1 2 3 4 5 6 7 8; do
 sleep 15
 systemctl is-active --quiet dog-art.service
 [ "$(systemctl show dog-art.service -p NRestarts --value)" = 0 ]
 case "$sample" in 4|8) runuser -u dog-art -- "$release/venv/bin/dog-art" --config /etc/dog-art/app.toml --secrets-file /etc/dog-art/.env status --redact;; esac
done
python3 -I "$protected/scripts/inspect-live.py"
systemctl show dog-art.service -p User -p ActiveState -p SubState -p NRestarts -p WorkingDirectory
systemctl show dog-art-reset.service -p Result -p ExecMainStatus
systemctl list-timers dog-art-reset.timer --no-pager
changed=0
trap - EXIT HUP INT TERM
printf '%s\n' 'Approved-as-ready release running. Pending appearances, QA holds and spending limits retained. No additional controlled paid test.'

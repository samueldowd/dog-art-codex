# Prerequisites, access and Computer Use preparation

Run preflight before implementation dependencies or production changes. Record observations in `docs/PREFLIGHT.md` with UTC time, target and redacted evidence. This authoring task did not connect to CT112 or Proxmox. No `C:\Users\Sam\.ssh\config` existed on the authoring host when checked; the user's named `proxmox-host` connection may be available on a different host or through the Codex app's SSH environment.

## 1. Prepare the execution host

- Use a Codex session with a real project directory, shell access, Git, Python tooling and outbound access to required official package/model/API endpoints.
- Enable the relevant SSH connection or make verified OpenSSH aliases available to the process that runs commands. An app connection and a local SSH alias are not automatically interchangeable.
- Make this entire package readable, including assets/templates. Read inherited `AGENTS.md` and skills before acting.
- Read build/access/deployment settings from `config/build.toml` and service settings from `config/app.toml`. Create the single ignored `config/.env` from its blank example only if absent. Verify `.gitignore` before secrets are supplied; preserve existing values and do not print them.
- Configure the client's actual permissions to permit the project checkout and approved CT112 actions. A prompt cannot override a sandbox, network restriction, SSH ACL, sudo rule, browser permission or approval rejection.
- Keep approval prompts usable. Do not use global unrestricted access or disabling approvals as a troubleshooting shortcut.
- Record available subagent, SSH, browser/Computer Use, Frigate and HA tools. Missing an optional connector does not prove the underlying service is absent.
- Keep human login/MFA available for genuine authentication blockers. Do not ask the user to paste private keys or API keys into chat.

## 2. Identify the target before writes

The deployment target is **CT112 on Debian**, not the Proxmox host and not the Windows authoring directory.

Preferred route, once `CT112_SSH_ALIAS` is configured:

~~~sh
ssh -G CT112_ALIAS
ssh -o BatchMode=yes CT112_ALIAS 'hostname; id; cat /etc/os-release'
~~~

Replace `CT112_ALIAS` with the verified configured alias. Inspect effective SSH configuration without printing credentials or private-key content. `BatchMode=yes` avoids a hanging password prompt; if interactive credentials are genuinely required, involve the user through the supported authentication flow.

Required fallback when direct CT112 access fails:

~~~sh
ssh -o BatchMode=yes proxmox-host 'hostname; id; pct status 112'
ssh -o BatchMode=yes proxmox-host 'pct config 112'
ssh -o BatchMode=yes proxmox-host 'pct exec 112 -- /bin/sh -lc "hostname; id; cat /etc/os-release"'
~~~

These are preflight/read examples for a future build, not commands already executed. Filter sensitive config output and confirm `pct` privilege using existing authorized root/sudo access. If sudo is required, use existing permitted scope and a noninteractive probe; do not change sudoers to bypass a denial.

Distinguish:
- **SSH route unavailable, CT112 running:** `pct exec 112 -- ...` is a valid container-local fallback.
- **CT112 stopped:** report and ask whether to start it; `pct exec` cannot run a stopped container.
- **Wrong Proxmox node / CT112 absent:** resolve the owning node from permitted inventory; do not recreate container 112.
- **Host-key unknown or changed:** verify the fingerprint through a trusted channel. Do not use `StrictHostKeyChecking=no` or erase known-host entries blindly.
- **Insufficient pct/sudo authority:** record the exact missing action and request narrow access.
- **Execution on proxmox-host succeeds:** every application command must still run inside `pct exec 112`. Do not install Python packages or the service on the host.

Avoid shell-string interpolation of event IDs, camera names, credentials or user/model text. Prefer fixed argument arrays, validated values, scripts transferred to a verified path, and explicit `--` argument separators where supported.

## 3. Inspect CT112's existing environment

Record:
- Debian release, architecture, Python version and supported virtual-environment tooling.
- CPU, RAM, free disk, existing GPU/acceleration access and current workload.
- Existing services/users/applications, available ports and ownership of proposed install/data paths.
- Time synchronization, timezone support and the application timezone `America/New_York`.
- Existing Git checkout/remotes/changes and any prior dog-art installation.
- Existing FFmpeg/video support and a real test decode.
- Connectivity and authenticated read access to Frigate, MQTT if used, Ollama and the HA SMB share.
- DNS/TLS trust and outbound OpenAI/package/model access.
- File-lock/rename behavior, disk capacity and backup location for SQLite and portraits.

Never upgrade the entire OS or Python installation to satisfy a preference. Use the installed supported version and an isolated venv; document a minimal compatible alternative if a dependency needs it.

## 4. Minimum application permissions

Use a dedicated proposed service user `dog-art` and application-scoped ownership:
- Read project release/config and protected credential files.
- Write its own state, cache, private fixtures, archives and publication staging.
- Reach authorized local services and OpenAI.
- Read and replace its single managed HA collage file through supplied Samba credentials.
- Manage only its own systemd service/timer through existing administrator authority.

Target paths such as `/opt/dog-art`, `/etc/dog-art` and `/var/lib/dog-art` are proposed defaults, not verified existing directories. Inspect before creating or reusing them.

Do not grant passwordless unrestricted sudo, change LXC privilege/nesting/AppArmor/network settings, alter another service, open internet ports, or reboot hosts/VMs to make the application work.

Prefer Python's application-level SMB client if no approved mount exists. An unprivileged LXC may not permit a kernel CIFS mount; that does not require weakening its isolation. Reuse an existing approved mount only after verifying its target and permissions.

## 5. Git and repository preparation

- Verify Git runs on the selected development host. GitHub credentials available to a connector do not automatically authenticate CT112's Git CLI.
- Verify the intended project repository/path/owner and existing branches. Do not reuse `samueldowd/fpa`; it is a reference project only.
- Configure/use an existing verified author and signing policy. Leave unknown identity values blank until supplied or discovered from legitimate project config.
- Verify any configured remote's repository and permissions without embedding tokens in its URL.
- An intentionally empty repository is valid for this greenfield Python project. Create the initial project checkpoint after setting ignore rules.
- If the remote is unavailable, continue in a dedicated local Git repository. Remote publication status must remain explicit.
- Give the Codex client access to any worktrees it is actually allowed to create; follow host/app worktree instructions.
- The primary agent owns shared-checkout Git state. Delegated workers must not switch branches or stage/commit concurrently.

## 6. Service prerequisites

| Dependency | Required verification |
|---|---|
| Frigate | Version, base URL/auth mode, camera IDs, dog detection on the selected cameras, available snapshots/recordings and API permissions. |
| MQTT | Broker/topic prefix/TLS/auth if using it; confirm a genuine event payload. If unavailable, evaluate authenticated API polling with equivalent dedup/backfill before declaring a blocker. |
| Ollama | Host `192.168.7.134`, actual scheme/port, selected tag, image-input capability and resource availability. Do not silently switch to a different model or cloud service. |
| OpenAI | API credential supplied securely, accessible image model with transparent PNG support, verified current pricing/limits and explicit numeric build/runtime spending/call bounds. |
| Samba / HA | HA server/share mapping, credentials, `kitchen-tv` subfolder, owned-file permissions, unrelated existing images and slideshow refresh behavior. |
| Assets | Actual access to the generated style art and optional private video fixtures; cross-host attachment paths must be transferred deliberately. |

If dog detection/recordings are absent, prepare the exact narrow Frigate configuration proposal and request the necessary scope before applying it. Do not silently change cameras, recording retention or detection models.

## 7. Computer Use and visual verification

Computer Use is a build-time verification aid, not a runtime dependency.

Preparation for the user:
1. Enable the Computer Use/browser capability on the host running Codex and grant its normal app/browser permissions.
2. Open the existing Home Assistant Kitchen TV dashboard and, when useful, Frigate/Proxmox pages in a supported accessible browser.
3. Sign in through the normal login/MFA flow. Supply a dashboard URL and view/card location without sharing passwords in documents.
4. Keep the target browser session available for the live acceptance window.

Preparation for Codex:
1. Read the current installed Computer Use skill and tool documentation. Available native and browser APIs differ by host/session; do not copy this author's runtime-specific initialization as a universal API.
2. Identify the actual browser/tab using the tool's inventory or explicit user reference. Do not guess screen content or claim to have seen a page without a real read/screenshot.
3. Prefer SSH, purpose-built APIs or connectors for system operations. Use browser interaction for the existing slideshow's visible result.
4. Capture the image before/after publication, wait through the slideshow's actual cycle and record the displayed revision/URL and screenshot.
5. Test refresh/caching behavior. If a card change is necessary, prepare a surgical, reviewable change and ask for that scope; preserve layout and unrelated controls.
6. A remote/headless Codex worker cannot assume it can control the user's desktop. If browser tools are unavailable, try a permitted read-only browser route; otherwise mark visible dashboard acceptance blocked and request access.
7. Do not install an alternative remote-control daemon, scrape browser credentials, disable auth, or use an undocumented UI automation workaround.

If UI verification is the only missing gate, finish independent implementation/testing/docs and provide an exact bounded verification request. Do not relabel a copied PNG as a visually verified dashboard.


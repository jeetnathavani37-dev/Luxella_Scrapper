# Server hardening: firewall + SSH lock-down

**Goal:** The server that holds the Shopify, Supabase and GitHub keys accepts logins **only with the founder's SSH
key**, blocks everything else at the firewall, and auto-bans brute-force IPs. A guessed or leaked password then
can't take over the store.

**Why now (read-only checks, 2026-10-07):**
- **Brute force is live:** **12,155 failed SSH logins in the last 24 h from 47 IPs** (`journalctl -u ssh`).
- **Password login is ON.** `sshd -T` shows `passwordauthentication yes`.
  - The cause is a config clash. `/etc/ssh/sshd_config.d/50-cloud-init.conf` says `yes`, and it is read before
    `60-cloudimg-settings.conf`, which says `no`. In sshd the first value wins.
  - `permitrootlogin yes`.
- **The founder never uses a password.** All **51 successful logins in 24 h were `publickey`**, and
  `authorized_keys` has 2 keys.
- **Firewall:** `ufw` is **inactive**.
- **Only SSH is exposed today.** The only public listener is `:22`. Every app (n8n, Chatwoot, Coolify, Uptime
  Kuma, NocoDB, openGym, DeerFlow, claude-mem…) is bound to `127.0.0.1`. This is luck plus earlier care, not a
  rule. One wrong `ports:` line in a compose file would publish an app to the internet, and Docker bypasses ufw.

## In scope
1. **SSH: key-only.**
   - Set `PasswordAuthentication no` in `50-cloud-init.conf`, the file that currently wins. Backup first to
     `/root/backups/2026-10-07/sshd/`.
   - Set `PermitRootLogin prohibit-password`: root via key only, which is how the founder logs in today.
   - Validate with `sshd -t` before the reload.
   - **Lock-out guard:**
     1. reload, not restart, so the current session stays alive;
     2. **the founder opens a NEW SSH session and confirms it works before anything else is closed;**
     3. if it fails, restore the backup from the still-open session.
2. **ufw firewall.**
   - `default deny incoming` / `allow outgoing`, plus `ufw limit 22/tcp` (rate limit). No other inbound ports.
   - Enable it only **after** confirming that rule 22 is in place, from the open session.
3. **fail2ban** (apt, ~30 MB RAM).
   - `sshd` jail: ban for 1 h after 5 failures in 10 min.
   - `ignoreip` holds the founder's current IP, read from `$SSH_CLIENT` of the live session.
4. **Docker guard.**
   - Add a check to the daily report: a "public ports" line that lists any listener not on 127.0.0.1/::1 other
     than :22, plus any container port published on 0.0.0.0.
   - A new public port makes the report **bad** the next morning.
   - This is a small read-only addition with its own test, so the gap where Docker bypasses ufw gets noticed.
5. **Docs:** a runbook section on how to get back in if locked out (the provider's web console), and an entry in
   DECISIONS.md.

## Out of scope
- Changing the SSH port, setting up a VPN or Tailscale, 2FA.
- The Docker/ufw integration package (`ufw-docker`). The daily-report guard covers it while every app stays on
  localhost.
- Opening ports for public apps (Chatwoot or a domain for openGym). That needs its own spec with HTTPS/Caddy.
- OS auto-updates (unattended-upgrades): check separately.

## Acceptance checks
1. `sshd -T` shows `passwordauthentication no` and `permitrootlogin without-password` (prohibit-password).
2. **The founder's new SSH session works with the key.** A password login attempt is refused:
   `ssh -o PubkeyAuthentication=no root@<server>` gives "Permission denied (publickey)".
3. `ufw status verbose` shows deny incoming, `22/tcp LIMIT`, and nothing else open.
4. **From outside**, every app port is closed: a GitHub Actions runner probes `nc -zv` on 5678, 3060, 8010, 8095,
   2026 and 37700. Port 22 is open.
5. `fail2ban-client status sshd` shows the jail active. After 24 h, banned IPs > 0 and failed logins drop sharply.
6. All local services keep working: n8n, Chatwoot, Coolify, Uptime Kuma, the daily report and the deal finder.
   Outbound calls to GitHub, Supabase, Shopify and ntfy are unaffected.
7. The daily report shows no `public ports` problem; its Data line shows `ports @ HH:MM`, so the check ran. The offline test proves that a fake 0.0.0.0:8080 listener
   makes it bad.

## Writes to production
**Server config only:** sshd config files, ufw rules, a fail2ban jail. There are **no** Shopify or Supabase
writes.

**Undo:**
- `ufw disable`;
- restore `/root/backups/2026-10-07/sshd/*`, then `systemctl reload ssh`;
- `systemctl disable --now fail2ban`.

## Risks
- **Lock-out.** This is the big one. Mitigations: the founder never uses a password today (51/51 logins by key);
  reload instead of restart; a new session is tested while the old one stays open; backups; the provider console
  as a last resort. **The founder must be present** for this step.
- **The founder's IP changes and fail2ban bans him.** That only happens after 5 failures, and key logins don't
  fail. `ignoreip` covers the current IP, and the console is the fallback.
- **A service breaks because something was quietly listening publicly.** The read-only check found none, and
  check 6 verifies it.
- **The GitHub Actions `@claude` agent or webhooks need inbound access.** They don't: all of them are outbound
  from GitHub's side, or polling.

## Rollout
1. The founder approves the spec **and picks a time when he is at the SSH terminal.**
2. Backups first. Then SSH (reload), and the founder tests a new session.
3. Then ufw, then fail2ban.
4. Run the outside port probe (check 4) and check every service (check 6).
5. PR for the daily-report "public ports" guard: reviewer, CI, founder merge.

## Status (2026-10-07)
- **Done and verified on the server, with the founder at the terminal:**
  - SSH key-only; the founder's new key session was confirmed at 18:09:30;
  - ufw (22 rate-limited, plus 10.0.0.0/8 for the internal key client 10.0.1.5);
  - fail2ban (2 IPs banned at once);
  - all local services re-checked.
- **PR:**
  - daily-report `ports` reader + "public ports" bad item;
  - `.github/workflows/port-probe.yml` for acceptance check 4. It needs the repo secret `SERVER_HOST`, which the
    founder adds; it is not stored in the public repo.

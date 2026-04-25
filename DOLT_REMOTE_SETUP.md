# Beads + DoltHub Remote Setup

This guide covers connecting a beads-managed dolt database to a DoltHub remote so your issue tracker is backed up off-machine.

---

## Prerequisites

- [Beads CLI](https://beads.sh) installed (`bd` in PATH)
- [Dolt CLI](https://docs.dolthub.com/introduction/installation) installed (`dolt` in PATH)
- A [DoltHub account](https://www.dolthub.com) (free)
- Beads already initialized in your project (`bd init` done)

> **Embedded vs server mode:** Modern beads (v1.x) uses embedded mode by default — no separate dolt server.
> Check `cat .beads/metadata.json` for `dolt_mode`. Embedded repos live at `.beads/embeddeddolt/<db-name>/`.
> Server-mode repos live at `.beads/dolt/`. Adjust paths below accordingly.

---

## 1. Create the DoltHub Repository

Go to [dolthub.com/repositories/new](https://www.dolthub.com/repositories/new) and create a new repository. Name it something like `<project-name>-beads`. Note your DoltHub **username** exactly as shown on your profile page.

---

## 2. Authenticate Dolt with DoltHub

Generate a key-pair credential and verify it reaches DoltHub:

```bash
dolt creds new
dolt creds check --endpoint doltremoteapi.dolthub.com:443
```

The check output shows the username your credentials resolve to:

```
Success.
  User: your-username
  Email: you@example.com
```

**Important:** The `User:` value here is your canonical DoltHub username — use it in the remote URL in the next step, not the username you type when logging in.

If the check fails, go to [dolthub.com/settings/credentials](https://www.dolthub.com/settings/credentials), copy the public key from `dolt creds ls`, and add it there.

---

## 3. Add the Remote

Use `bd dolt remote add` which registers the remote in both beads' config and the native dolt repo:

```bash
bd dolt remote add origin https://doltremoteapi.dolthub.com/<your-dolthub-username>/<repo-name>
```

Verify it was saved (find the correct path first):

```bash
# Embedded mode (beads v1.x default)
cat .beads/embeddeddolt/sishya/.dolt/repo_state.json

# Server mode (legacy)
cat .beads/dolt/.dolt/repo_state.json
```

---

## 4. Push

Push directly with the dolt CLI — more reliable than `bd dolt push`:

```bash
# Embedded mode
cd .beads/embeddeddolt/sishya && dolt push origin main && cd -

# Server mode
cd .beads/dolt && dolt push origin main && cd -
```

Add a shell alias for convenience (update the path to match your project):

```bash
# ~/.zshrc or ~/.bashrc
alias bdpush='cd /path/to/your/project/.beads/embeddeddolt/sishya && dolt push origin main && cd -'
```

---

## Troubleshooting

### "permission denied" when pushing

**Cause 1 — Wrong DoltHub username in remote URL.**
Run `dolt creds check --endpoint doltremoteapi.dolthub.com:443` and check the `User:` field. That is the exact username to use in the remote URL. It may differ from the email or display name you use to log in.

Fix: remove and re-add the remote with the correct username.

```bash
cd .beads/dolt
dolt remote remove origin
dolt remote add origin https://doltremoteapi.dolthub.com/<correct-username>/<repo-name>
cd -
bd dolt remote remove origin --force
bd dolt remote add origin https://doltremoteapi.dolthub.com/<correct-username>/<repo-name>
```

**Cause 2 — DoltHub repository doesn't exist yet.**
The push will fail with `permission denied` even if credentials are valid if the repository hasn't been created on DoltHub. Create it at [dolthub.com/repositories/new](https://www.dolthub.com/repositories/new) first.

**Cause 3 — Credential public key not added to DoltHub.**
After `dolt creds new`, you must manually add the public key to your DoltHub account. Run `dolt creds ls` to get the key ID, then go to [dolthub.com/settings/credentials](https://www.dolthub.com/settings/credentials) to add it.

---

### "must set DOLT_REMOTE_PASSWORD environment variable"

This error appears when using HTTP basic auth (`--user` flag) instead of key-pair credentials. You don't need `DOLT_REMOTE_PASSWORD` if you're using dolt key-pair creds (the preferred method). Generate credentials with `dolt creds new` and follow the steps above.

---

### Remote URL mismatch between SQL and CLI

If `bd dolt remote remove origin` shows:

```
Error: remote "origin" has conflicting URLs:
  SQL: https://doltremoteapi.dolthub.com/old-name/repo
  CLI: https://doltremoteapi.dolthub.com/new-name/repo
```

Force-remove both and re-add:

```bash
bd dolt remote remove origin --force
bd dolt remote add origin https://doltremoteapi.dolthub.com/<username>/<repo-name>
```

This syncs beads' SQL-stored remote with the native dolt `repo_state.json`.

---

### `bd dolt push` connects to the wrong port / times out

If `bd dolt push` times out with a MySQL connection error on an unexpected port, bypass it and use the dolt CLI directly:

```bash
cd .beads/dolt && dolt push origin main && cd -
```

The dolt CLI reads credentials from `~/.dolt/creds/` and the remote from `.beads/dolt/.dolt/repo_state.json` — both of which are configured correctly after following this guide.

---

### Remote is missing after `bd backup restore` or repo re-init

Restoring from a beads JSONL backup restores issues but not the dolt remote config. Re-run steps 3 and 4 after any restore.

---

## Pulling on Another Machine

```bash
# Clone the project repo (which contains .beads/)
git clone <your-project-repo>
cd <project>

# Pull beads data from DoltHub
bd dolt start
cd .beads/dolt && dolt pull origin main && cd -
```

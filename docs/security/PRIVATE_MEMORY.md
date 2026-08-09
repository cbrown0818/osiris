# OSIRIS Private Memory Boundary

OSIRIS stores conversations and long-term memory locally in PostgreSQL and Qdrant.
Runtime data, credentials, exports, database dumps, encrypted archives, and recovery
keys must never be committed to Git.

## API access

All API routes except `/` and `/health` require the local `OSIRIS_API_TOKEN`.
The browser keeps this token in `sessionStorage`, so it is discarded when the tab
session ends.

## Backups

Run:

```bash
scripts/backup-osiris.sh
```

Encrypted archives are written outside the repository to:

```text
/mnt/vault/osiris-private-backups/
```

The symmetric recovery key is stored at:

```text
~/.config/osiris/backup-passphrase
```

Copy that recovery key to an offline encrypted location. Do not place it in Git,
cloud notes, chat, screenshots, or the backup directory itself.

## Git safeguards

Version-controlled hooks under `.githooks/` call
`scripts/git-privacy-check.sh`.

The pre-commit hook scans staged content.

The pre-push hook scans the complete reachable Git history.

They reject private user data, conversation exports, runtime databases,
credentials, secret-like content, prohibited personal media, and encrypted
private archives before that material can be committed or pushed.

# Authentication throttle retention

`AuthThrottle` stores keyed authentication failure buckets. Each bucket is reused while its fixed 15-minute window is active, but identity and IP sprays can create many distinct keys. The retention command retires only rows whose window is older than the selected age and whose `blocked_until` is empty or has passed. A bucket blocked at the time of pruning remains in place so pruning cannot remove an active lockout.

Run from the deployed application release with the normal production environment and database credentials:

```sh
python manage.py prune_auth_throttles
```

The default is a dry run: it reports the bounded eligible count, cutoff and database timestamp without deleting rows. Review that output, then explicitly apply one batch:

```sh
python manage.py prune_auth_throttles --older-than-days 30 --batch-size 1000 --apply
```

The age must be 1–3650 days and each run is limited to 1–10000 rows. If more eligible rows remain, the command says so; schedule repeated invocations to drain older backlog gradually. The default 30-day age is comfortably beyond the 15-minute throttle window. The query uses the database server clock. Output contains counts and timestamps only, never bucket keys, usernames, email addresses or IP addresses.

For production, an operator may configure a host-managed systemd timer or cron entry to run the explicit `--apply` command daily, with output routed to the deployment's existing restricted operations log. Keep the interval and row limit modest, alert on command failures, and review a dry run before the first applied run. This repository does not install or activate any external timer or automation.

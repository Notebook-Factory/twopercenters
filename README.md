# twopercenters

The Evidence dashboard over the Ioannidis "top 2% of scientists" tables. It
serves 15 editions (career and single-year, 2017 to 2024) and 2,730,673 fact
rows out of Postgres, with a small Elasticsearch index used for one thing
only: the fuzzy author typeahead.

There are two data stores and they are not interchangeable:

* **Postgres** holds everything the dashboard draws: the two fact tables, the
  dimension tables, and three materialized views (`group_metrics`,
  `dropdown_options`, `dropdown_stats`). The app raises at import with
  "DATABASE_URL is not set" if it cannot reach one.
* **Elasticsearch** holds one index, aliased `authors`, carrying author names
  and the few fields the typeahead filters on. It is about 100 MB and holds
  no metrics. The blob-era `career` and `singleyr` indices are gone; see
  "Rebuilding the legacy indices" at the bottom if you ever need them back.

## Local development

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
make up                       # Postgres on :5433, Elasticsearch on :9201
cp .env.example .env          # DATABASE_URL and ELASTICSEARCH_URL for the above
make build-all                # migrate, load, export Parquet, build the index
.venv/bin/python app.py
```

`make build-all` needs `data_clean/`, which is 1.9 GB and gitignored. It is
produced from `data_raw/` (1.1 GB of source spreadsheets) by
`fetch_sources.py` and `clean_sources.py`. A full load takes about nine
minutes.

Tests: `.venv/bin/pytest tests/ -v`, about ten minutes for 118 tests. They run
against `TEST_DATABASE_URL`, a separate database, because two of the modules
drop and recreate the public schema.

## Deploying to dokku

Nothing below is optional, and the order matters. The app needs both services
linked before its first boot, and it needs data in Postgres before that boot
does anything useful, because `pages/home.py` queries the database while it is
still being imported.

### 1. Create the app and both services

```bash
# on the dokku host
sudo dokku plugin:install https://github.com/dokku/dokku-postgres.git postgres
sudo dokku plugin:install https://github.com/dokku/dokku-elasticsearch.git elasticsearch

dokku apps:create twopercenters

dokku postgres:create citedb-pg
dokku postgres:link citedb-pg twopercenters      # sets DATABASE_URL

export ELASTICSEARCH_IMAGE="elasticsearch"
export ELASTICSEARCH_IMAGE_VERSION="7.17.23"
dokku elasticsearch:create citedb
dokku elasticsearch:link citedb twopercenters    # sets ELASTICSEARCH_URL
```

`dokku postgres:info citedb-pg` and `dokku elasticsearch:info citedb` print
the internal URLs. The linked app gets `DATABASE_URL` and
`ELASTICSEARCH_URL` in its environment; `db/connection.py` reads the first
and `citations_lib/utils.py` the second, and neither has a fallback, on
purpose.

Give Postgres room: the database is about 2.6 GB loaded, and the restore in
step 3 needs working space on top of that.

### 2. Push the code

```bash
git remote add dokku dokku@[vm.floating.ip]:twopercenters
git push dokku relational-core:master
```

The first deploy will build and then fail its health check, because the
database is empty and `pages/home.py` reads it at import. That is expected at
this point. Finish step 3 and `dokku ps:restart twopercenters`.

### 3. Get the data onto the host

`data_clean/` (1.9 GB), `data_raw/` (1.1 GB) and `data_parquet/` are all
gitignored, so the push in step 2 carried no data whatsoever. Building on the
host is possible but it means shipping 1.1 GB of source spreadsheets there and
spending about nine minutes of host CPU on a box that also runs other
dashboards. Don't. Build locally and move the finished database.

```bash
# locally: build, then dump
make build-all
pg_dump --format=custom --no-owner --no-privileges \
        "$DATABASE_URL" --file twopct.dump          # about 1.2 GB

# copy it to the host
scp twopct.dump user@[vm.floating.ip]:/tmp/twopct.dump
```

```bash
# on the dokku host: restore into the linked service
dokku postgres:import citedb-pg < /tmp/twopct.dump
```

`dokku postgres:import` runs `pg_restore` into the service's database. It
does not run migrations and does not need to: the dump carries the schema,
the `schema_migrations` rows and all three materialized views already
populated.

If you would rather migrate and load on the host instead, the equivalent is:

```bash
dokku run twopercenters python db/migrate.py
# ... having first got data_clean/ onto the host somehow ...
dokku run twopercenters python pipeline/build_relational.py data_clean
```

`db/migrate.py` applies `db/migrations/*.sql` once each in sorted filename
order and is safe to run against a database that is already up to date.
`build_relational.py` refuses to run if it finds no editions under
`data_clean/`, rather than quietly producing an empty database, so you will
be told rather than left guessing.

### 4. Build the search index

The typeahead reads the `authors` alias, which lives in Elasticsearch and is
therefore not in the Postgres dump.

```bash
dokku run twopercenters python pipeline/build_search_index.py
```

It reads Postgres and writes a fresh concrete index, then repoints the alias
in one atomic `update_aliases` call, so the running app never sees the alias
pointing at nothing. Verify:

```bash
dokku elasticsearch:connect citedb   # or curl the internal URL
curl http://dokku-elasticsearch-citedb:9200/_cat/aliases
```

### 5. Start it

```bash
dokku ps:restart twopercenters
dokku letsencrypt:enable twopercenters
```

### What the web process actually runs

```
web: gunicorn app:server -c cfg.py
```

`cfg.py` is the gunicorn config, and it is wired in deliberately: it carries
a `post_fork` hook that gives every worker its own database connection.
`preload_app` is on, so gunicorn imports the app in the master process and
forks the workers from it, and `pages/home.py` opens a connection during that
import. Without the hook (and without `app.py` closing the connection at the
end of its own import) both workers would share one libpq socket and
interleave their queries on it. `tests/test_no_shared_connection.py` holds
that invariant. `cfg.py` deliberately sets no `bind`: gunicorn already
defaults to `0.0.0.0:$PORT`, which is what dokku provides.

## Rebuilding the legacy indices

The blob-era `career` and `singleyr` Elasticsearch indices were deleted once
the migration was verified to work without them (RULING R26). They existed
only as the "before" side of the latency benchmark. If that baseline is ever
needed again, `bench/build_legacy_index.py` rebuilds both of them directly
from `data_clean/`, with the same mapping and the same zlib+base64 `data`
field the original indexer used:

```bash
ES_URL_LOCAL=http://localhost:9201 .venv/bin/python bench/build_legacy_index.py
ES_URL_LOCAL=http://localhost:9201 .venv/bin/python bench/latency.py \
    --mode legacy --out bench/baseline.json
```

See `bench/README.md` for what the harness measures and why "legacy" mode
imports a pinned copy of the old query code rather than today's
`citations_lib.utils`. Nothing in the dashboard reads those indices any more,
and nothing should: a fresh deployment will not have them.

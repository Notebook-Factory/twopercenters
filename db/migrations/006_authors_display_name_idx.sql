-- An index for the dashboard's exact-name lookup.
--
-- Once a user picks a name out of the typeahead dropdown, the dashboard has
-- that author's display name exactly and only needs to look it up. It used
-- to do that with the same fuzzy Elasticsearch multi_match the typeahead
-- uses, which scores candidates across all 818,667 documents in the
-- `authors` alias; profiling put that at 79% of the whole fetch. An exact
-- lookup is what Postgres is for, and this is the index it reads.
--
-- The match is on authfull_display rather than name_normalized because the
-- two are not guaranteed to agree: build_relational.py writes one row per
-- author_id while an author's raw name can be spelled differently in
-- different editions ("Ioannidis, Yannis" and "Ioannidis, Yannis E."), so a
-- stored name_normalized may have been derived from a different edition's
-- spelling than the stored authfull_display. authfull_display is also the
-- exact string the typeahead hands back, so matching it needs no agreement
-- between two normalizers.
create index if not exists authors_authfull_display_idx
    on authors (authfull_display);

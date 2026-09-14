from rdl import spec


def test_career_metrics_is_the_fact_table():
    t = spec.TABLES["career_metrics"]
    assert t.pkey == "metric_id"
    assert t.time_col == "observation_date"
    assert t.fkeys["author_id"] == "authors"
    assert t.fkeys["institution_id"] == "institutions"
    assert t.fkeys["edition_id"] == "editions"


def test_ns_columns_are_dropped():
    """Fifteen non-self-citation restatements of the main metrics. They
    correlate almost perfectly with their bare counterparts."""
    t = spec.TABLES["career_metrics"]
    assert len([c for c in t.drop_columns if c.endswith("_ns")]) == 15


def test_retraction_columns_survive_the_drops():
    """nc_rw is the centrepiece target. Dropping it here would be silent."""
    t = spec.TABLES["career_metrics"]
    for col in ("np_rw", "nc_rw", "nc_to_rw"):
        assert col not in t.drop_columns


def test_provenance_columns_are_dropped_from_editions():
    """sha256 and source_filename have one distinct value per row. They are
    provenance for humans and pure noise to a model."""
    t = spec.TABLES["editions"]
    assert "sha256" in t.drop_columns
    assert "source_filename" in t.drop_columns


def test_splits_are_the_edition_boundaries():
    assert str(spec.VAL_TIMESTAMP.date()) == "2022-12-31"
    assert str(spec.TEST_TIMESTAMP.date()) == "2023-12-31"


def test_every_fkey_target_is_a_declared_table():
    for name, t in spec.TABLES.items():
        for col, dest in t.fkeys.items():
            assert dest in spec.TABLES, f"{name}.{col} -> {dest}"


def test_subfields_link_to_fields():
    """subfields carries a field_id foreign key. Missing it would leave the
    subfield dimension dangling off the taxonomy it belongs to."""
    assert spec.TABLES["subfields"].fkeys["field_id"] == "fields"


def test_declared_columns_exist_in_the_exported_parquet():
    """Guards against a stype or drop naming a column that is not there,
    which would otherwise fail much later during graph construction."""
    import pyarrow.parquet as pq
    for name, t in spec.TABLES.items():
        cols = set(pq.ParquetFile(f"data_parquet/{name}.parquet").schema_arrow.names)
        for col in list(t.stypes) + t.drop_columns + list(t.fkeys) :
            assert col in cols, f"{name}.{col} not in the parquet export"
        if t.pkey:
            assert t.pkey in cols, f"{name}.{t.pkey} missing"

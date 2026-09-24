from rdl import spec


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


def test_no_column_needs_a_text_embedder():
    """Every declared stype must be one the graph can encode without
    sentence-transformers. A stray 'text' would reintroduce that dependency
    silently at graph-build time."""
    for name, t in spec.TABLES.items():
        assert "text" not in t.stypes.values(), name


def test_identity_columns_are_dropped_not_encoded():
    """authfull_display is 52% row-unique, inst_name is 100% row-unique.
    Encoding either teaches the model to memorise rather than generalise,
    and the name columns additionally carry name-origin signal."""
    assert "authfull_display" in spec.TABLES["authors"].drop_columns
    assert "name_normalized" in spec.TABLES["authors"].drop_columns
    assert "surname" in spec.TABLES["authors"].drop_columns
    assert "inst_name" in spec.TABLES["institutions"].drop_columns


def test_dropped_columns_are_never_also_typed():
    """A column cannot be both dropped and given a semantic type; one of the
    two would silently win."""
    for name, t in spec.TABLES.items():
        overlap = set(t.drop_columns) & set(t.stypes)
        assert not overlap, f"{name}: {overlap}"

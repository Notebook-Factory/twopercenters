"""Measure dashboard-facing latency for the two interactions users feel.

Phase one is keystroke-to-dropdown: the author typeahead. Phase two is
selection-to-chart: fetching one author's metrics. Both are measured the same
way before and after the migration, so the comparison is like for like.

Run as a script to record a baseline:

    python bench/latency.py --mode legacy --out bench/baseline.json

``--mode legacy`` wires the typeahead and fetch phases to the blob-era
Elasticsearch path (``citations_lib.utils.get_es_results`` /
``es_result_pick`` against the ``career``/``singleyr`` indices, exactly as
``pages/`` calls them today).

``--mode current`` is meant to wire the same two phases to the post-migration
lookup path. That path does not exist yet, so this mode fails cleanly with a
clear message instead of a raw traceback.
"""
import argparse
import json
import statistics
import time


# RULING R14: the original 6-term x 5-repeat sample made p95 effectively a
# single observation (repeat runs of identical legacy code against identical
# data swung p95 by 2x in both directions). This set raises sampling to 12
# terms and mixes in the query shapes that behave differently at the ES
# layer: short 2-3 char prefixes that match thousands of authors ("an",
# "jo", "smi", "wan"), full surnames ("smith", "johnson", "chen", "garcia",
# "ioannidis"), one name carrying a diacritic ("müller"), and two deliberate
# typos so the fuzzy-matching path (fuzziness "auto") is actually exercised
# ("smtih", "ionnidis").
DEFAULT_TERMS = [
    "an", "jo", "smi", "wan",
    "smith", "johnson", "chen", "garcia", "ioannidis",
    "müller",
    "smtih", "ionnidis",
]
DEFAULT_REPEATS = 20


def _percentile(values, pct):
    ordered = sorted(values)
    index = min(int(round((pct / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


def warm(typeahead_fn, fetch_fn, terms, passes=1):
    """Run the term list through a stack and throw the timings away.

    Measured across three separate sessions, the *unchanged* legacy stack
    reported fetch p50 of 10.25ms, then 8.38ms, then 6.80ms. Legacy code and
    legacy data did not change between those runs; what changed is that
    Elasticsearch's filesystem cache and the OS page cache held more of the
    career/singleyr indices each time. Whichever stack is measured second, or
    measured more often, therefore looks faster, and a baseline that drifts
    downward on every re-measurement is not a baseline.

    So both stacks get the same treatment before anything is recorded: the
    same terms, the same number of passes, in the same process. A comparison
    where one side is warm and the other is cold is not a comparison.
    """
    for _ in range(passes):
        for term in terms:
            hits = typeahead_fn(term)
            if hits:
                fetch_fn(hits[0])


def measure_both(legacy, current, terms, repeats=5, warmup=1):
    """Measure both stacks in one process, interleaved term by term.

    Interleaving matters as much as the warm-up does. The two stacks used to
    be measured in separate runs minutes apart, so any drift in machine load
    over those minutes landed entirely on one side of the comparison. Here
    each term's legacy and current samples are taken microseconds apart and
    see the same machine.
    """
    legacy_typeahead, legacy_fetch = legacy
    current_typeahead, current_fetch = current

    warm(legacy_typeahead, legacy_fetch, terms, passes=warmup)
    warm(current_typeahead, current_fetch, terms, passes=warmup)

    samples = {'legacy_typeahead': [], 'legacy_fetch': [],
               'current_typeahead': [], 'current_fetch': []}

    for term in terms:
        for _ in range(repeats):
            for label, typeahead_fn, fetch_fn in (
                    ('legacy', legacy_typeahead, legacy_fetch),
                    ('current', current_typeahead, current_fetch)):
                started = time.perf_counter()
                hits = typeahead_fn(term)
                samples[f'{label}_typeahead'].append(
                    (time.perf_counter() - started) * 1000)
                if hits:
                    started = time.perf_counter()
                    fetch_fn(hits[0])
                    samples[f'{label}_fetch'].append(
                        (time.perf_counter() - started) * 1000)

    out = {"n": len(terms), "repeats": repeats, "warmup_passes": warmup,
           "mode": "both", "terms": list(terms)}
    for label in ('legacy', 'current'):
        for phase in ('typeahead', 'fetch'):
            values = samples[f'{label}_{phase}']
            out[f'{label}_{phase}_p50_ms'] = round(
                statistics.median(values), 2)
            out[f'{label}_{phase}_p95_ms'] = round(
                _percentile(values, 95), 2)
    return out


def measure(typeahead_fn, fetch_fn, terms, repeats=5):
    typeahead_ms, fetch_ms = [], []

    for term in terms:
        for _ in range(repeats):
            started = time.perf_counter()
            hits = typeahead_fn(term)
            typeahead_ms.append((time.perf_counter() - started) * 1000)

            if hits:
                started = time.perf_counter()
                fetch_fn(hits[0])
                fetch_ms.append((time.perf_counter() - started) * 1000)

    return {
        "n": len(terms),
        "repeats": repeats,
        "typeahead_p50_ms": round(statistics.median(typeahead_ms), 2),
        "typeahead_p95_ms": round(_percentile(typeahead_ms, 95), 2),
        "fetch_p50_ms": round(statistics.median(fetch_ms), 2),
        "fetch_p95_ms": round(_percentile(fetch_ms, 95), 2),
    }


def _legacy_fns():
    """The blob-era path: authfull typeahead and per-author fetch, exactly as
    citations_lib/single_author_layout.py and callback_templates.py called
    them against the career/singleyr Elasticsearch indices, before
    citations_lib.utils was migrated onto Postgres.

    This deliberately does NOT import from citations_lib.utils: that module
    has since been migrated (get_es_results now queries the `authors` alias
    with a filtered _source, and es_result_pick('data', ...) now reads
    Postgres). Importing the current module here would measure the new
    stack twice under two different labels instead of comparing it to the
    old one. bench/_legacy_es.py pins the pre-migration implementation
    (commit 9261573) so this mode still exercises the real old code path
    against the untouched career/singleyr indices.
    """
    from bench._legacy_es import get_es_results, es_result_pick

    def typeahead(term):
        result = get_es_results(term, ["career", "singleyr"], "authfull")
        return es_result_pick(result, "authfull") or []

    def fetch(author):
        results_career = get_es_results(author, "career", "authfull")
        data_career = es_result_pick(results_career, "data", None)

        results_singleyr = get_es_results(author, "singleyr", "authfull")
        data_singleyr = es_result_pick(results_singleyr, "data", None)

        return {"career": data_career, "singleyr": data_singleyr}

    return typeahead, fetch


def _current_fns():
    """The post-migration path. citations_lib.utils.get_es_results and
    es_result_pick do not exist in their new (relational-core) form yet, so
    this mode fails cleanly rather than with a raw traceback. Only
    ``--mode legacy`` is required to work for this task.
    """
    try:
        from citations_lib.utils import get_es_results, es_result_pick
    except ImportError as exc:
        raise SystemExit(
            "bench/latency.py --mode current: citations_lib.utils does not "
            "yet expose the post-migration lookup path "
            f"(import failed: {exc}). Re-run with --mode legacy, or come "
            "back to --mode current once the relational-core lookup lands."
        )

    def typeahead(term):
        try:
            result = get_es_results(term, ["career", "singleyr"], "authfull")
            return es_result_pick(result, "authfull") or []
        except Exception as exc:
            raise SystemExit(
                "bench/latency.py --mode current: typeahead call failed "
                f"({type(exc).__name__}: {exc}). The current implementation "
                "of get_es_results/es_result_pick is still the blob-era one "
                "and is not guaranteed to match the relational-core design; "
                "this mode is not expected to work yet."
            )

    def fetch(author):
        # exact=True mirrors what citations_lib/single_author_layout.py now
        # does: by the fetch phase the user has already picked a name out of
        # the dropdown, so the exact string is in hand and Postgres answers
        # it with one indexed read instead of Elasticsearch fuzzy-matching a
        # string that needs no matching. The legacy side keeps its fuzzy
        # implementation because that is genuinely what the old stack did;
        # what is being compared is the same user interaction, each stack
        # doing it the way that stack does it.
        try:
            results_career = get_es_results(author, "career", "authfull",
                                            exact=True)
            data_career = es_result_pick(results_career, "data", None)
            results_singleyr = get_es_results(author, "singleyr", "authfull",
                                              exact=True)
            data_singleyr = es_result_pick(results_singleyr, "data", None)
            return {"career": data_career, "singleyr": data_singleyr}
        except Exception as exc:
            raise SystemExit(
                "bench/latency.py --mode current: fetch call failed "
                f"({type(exc).__name__}: {exc}). This mode is not expected "
                "to work yet; use --mode legacy."
            )

    return typeahead, fetch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["legacy", "current", "both"],
                        required=True)
    parser.add_argument(
        "--warmup", type=int, default=1,
        help="passes of the term list to run and discard before recording, "
             "per stack (default 1). Only --mode both applies it, because "
             "only --mode both can warm the two stacks equally.",
    )
    parser.add_argument("--out", required=True, help="path to write the result JSON to")
    parser.add_argument(
        "--terms",
        nargs="+",
        default=DEFAULT_TERMS,
        help="typeahead search terms to measure (default: a fixed small set)",
    )
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    args = parser.parse_args()

    if args.mode == "both":
        result = measure_both(_legacy_fns(), _current_fns(), args.terms,
                              repeats=args.repeats, warmup=args.warmup)
    else:
        if args.mode == "legacy":
            typeahead_fn, fetch_fn = _legacy_fns()
        else:
            typeahead_fn, fetch_fn = _current_fns()

        result = measure(typeahead_fn, fetch_fn, args.terms,
                         repeats=args.repeats)
        result["mode"] = args.mode
        result["terms"] = args.terms

    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

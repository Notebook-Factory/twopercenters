import time
from bench.latency import measure


def test_measure_reports_percentiles_for_both_phases():
    def typeahead(term):
        time.sleep(0.002)
        return ["Ioannidis, John P.A."]

    def fetch(name):
        time.sleep(0.004)
        return {"c": 1.0}

    result = measure(typeahead, fetch, ["ioa", "ioan", "ioann"])

    assert result["n"] == 3
    assert result["typeahead_p50_ms"] >= 2.0
    assert result["fetch_p50_ms"] >= 4.0
    assert result["typeahead_p95_ms"] >= result["typeahead_p50_ms"]

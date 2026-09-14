import subprocess
import sys


def test_dashboard_import_pulls_in_no_ml_stack():
    """The dashboard reads predictions from Postgres. If torch ever appears
    in its import graph, a multi-gigabyte dependency has leaked into the web
    process, which serves requests and must stay small."""
    code = (
        "import app, sys;"
        "bad=[m for m in ('torch','relbench','torch_geometric','torch_frame')"
        " if m in sys.modules];"
        "assert not bad, bad;"
        "print('clean')"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True)
    assert out.returncode == 0, out.stderr
    assert "clean" in out.stdout

"""app_test — local-first GUI testing via image matching (SikuliX).

    from skills.app_test.generator import load_spec, to_sikulix_script, run
    run("tests/login_flow.json", out_dir="build")
"""

from skills.app_test.generator import (
    load_spec, to_sikulix_script, write_script, run, find_sikulix,
)

__all__ = ["load_spec", "to_sikulix_script", "write_script", "run", "find_sikulix"]

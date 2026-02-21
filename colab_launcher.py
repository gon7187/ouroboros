"""Launcher wrapper for local/Colab runs.

Runs colab_bootstrap_shim as __main__ so supervisor actually starts.
"""

import runpy

runpy.run_module("colab_bootstrap_shim", run_name="__main__")


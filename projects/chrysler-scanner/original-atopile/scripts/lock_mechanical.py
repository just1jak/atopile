"""Compatibility entry point: restore mechanical locks and visible references.

Use finish_board.py directly for new workflows. Footprint positions, electrical
connections and routing are preserved by both commands.
"""
from pathlib import Path
import runpy
runpy.run_path(str(Path(__file__).with_name('finish_board.py')),run_name='__main__')

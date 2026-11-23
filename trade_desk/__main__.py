"""Allows `python -m trade_desk` invocation."""
import sys
from .cli import main

sys.exit(main())

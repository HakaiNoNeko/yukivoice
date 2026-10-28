"""PyInstaller entry point (the package uses relative imports, so it can't be the script itself)."""
import sys

from yukivoice.app import main

sys.exit(main())

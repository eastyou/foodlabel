"""支持 ``python -m foodlabel`` 运行。"""

import sys

from foodlabel.cli import main

if __name__ == "__main__":
    sys.exit(main())

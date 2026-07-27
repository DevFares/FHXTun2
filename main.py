"""
Root main.py entry point.
Launches the asymmetric proxy system.
"""

import asyncio
from asymmetric_proxy.main import main

if __name__ == "__main__":
    asyncio.run(main())

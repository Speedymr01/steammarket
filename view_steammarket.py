import subprocess, sys, os
p = os.path.join(os.path.dirname(__file__), "steammarketapi.pyw")
subprocess.run([sys.executable, p, "--graph", "--no-enter-to-exit"])

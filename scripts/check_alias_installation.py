"""Install the compatibility wheel into a fresh host and verify dependency discovery."""

import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from certbot.compat import os


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    core_wheels = list((root / "dist").glob("certbot_dns_teo-*.whl"))
    alias_wheels = list((root / "dist").glob("certbot_dns_tencent_edgeone-*.whl"))
    if len(core_wheels) != 1 or len(alias_wheels) != 1:
        raise SystemExit("Build both packages into a clean dist/: uv build --all-packages --clear")
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required for installation verification")
    with TemporaryDirectory(prefix="edgeone-alias-check-") as directory:
        temporary = Path(directory)
        environment = temporary / "venv"
        python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([uv, "venv", "--python", sys.executable, str(environment)], check=True)
        # Resolve the core dependency from the built wheel, even before publication.
        # Only the alias is an install target; the resolver must pull in the core.
        constraints = temporary / "constraints.txt"
        constraints.write_text(
            f"certbot-dns-teo @ {core_wheels[0].resolve().as_uri()}\n", encoding="utf-8"
        )
        subprocess.run(
            [
                uv,
                "pip",
                "install",
                "--python",
                str(python),
                "--constraint",
                str(constraints),
                str(alias_wheels[0]),
            ],
            cwd=temporary,
            check=True,
        )
        subprocess.run(
            [str(python), str(root / "scripts/check_installation.py"), "--with-alias"],
            cwd=temporary,
            check=True,
        )


if __name__ == "__main__":
    main()

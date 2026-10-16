# Setting up on Windows with WSL

On Windows, work inside the Windows Subsystem for Linux. These steps were written on Ubuntu 22.04; after them, [CONTRIBUTING.md](../CONTRIBUTING.md#setup) applies unchanged.

Clone into the Linux filesystem (for example `~/src`), not onto a Windows drive under `/mnt`, where file access is much slower.

1. Open Ubuntu from PowerShell or Windows Terminal:

   ```powershell
   wsl -d Ubuntu-22.04
   ```

2. Install Java 21, git, Python's venv module and poppler (which provides `pdftotext`):

   ```bash
   sudo apt update
   sudo apt install -y openjdk-21-jdk git curl python3-venv poppler-utils
   java -version
   ```

3. Install the Clojure CLI:

   ```bash
   curl -L -O https://github.com/clojure/brew-install/releases/latest/download/linux-install.sh
   chmod +x linux-install.sh
   sudo ./linux-install.sh
   rm linux-install.sh
   clojure --version
   ```

4. Keep line endings as LF:

   ```bash
   git config --global core.autocrlf input
   ```

5. Follow [CONTRIBUTING.md § Setup](../CONTRIBUTING.md#setup), cloning both repositories into `~/src`. Put `export URPX_RATE_PLANS_VENV=~/.venvs/urpx-rate-plans` in `~/.bashrc` so new shells keep it.

For MinerU and spel, follow [AGENTS.md](../AGENTS.md#reading-a-tariff-pdf); spel's Linux binary is `spel-linux-amd64` on its releases page, and `spel install --with-deps` installs the browser with the system libraries it needs.

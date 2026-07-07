# Changelog

All notable changes to this project will be documented here.

---

## [0.4.1] - 2026-07-07

### ✨ Added (0.4.1)

- Migrated from `subprocess`/`ProcessBuilder` to [Appose](https://github.com/apposed/appose) for running InstanSeg
- Python environment now builds itself automatically on first run — no more manual `install.sh`/`install.bat` step
- `Environment path` override now accepts any environment type Appose can detect (pixi, conda/mamba, venv)

### 🔄 Changed (0.4.1)

- `_instanseg_runner.py` is now an importable function (`run_instanseg()`) instead of an `argparse` CLI script
- Errors now propagate as real Python exceptions with full tracebacks, shown directly in Fiji
- Main plugin script renamed to `Run_Instanseg_Fiji.py` for consistent display in the Fiji menu

### 🐛 Fixed (0.4.1)

- `OMP: Error #15` crash from PyTorch and numpy both initializing OpenMP
- Bio-Formats failing to read any file due to a JVM/import ordering bug
- Potential hang on Windows when importing `numpy`/`torch`/starting the JVM mid-task ([apposed/appose#23](https://github.com/apposed/appose/issues/23))
- `cjdk` occasionally fetching a JRE instead of a full JDK on Windows, missing `jar.exe`
- Garbled console output from a pixi manifest deprecation warning

---

## [0.3.0] - 2026-06-29

### ✨ Added (0.3.0)

- GitHub Actions release workflow — pushing a `v*` tag now builds and publishes `InstanSeg.zip` automatically with the correct folder name and locked dependencies
- Timestamped log lines in the Fiji Log window via `timed_log()`

### 🔄 Changed (0.3.0)

- Python environment is now installed **outside** the Fiji plugins folder to prevent Fiji's script discovery from picking up pixi environment files and cluttering the search results
  - Windows: `C:\Users\<you>\AppData\Roaming\InstanSeg\`
  - Linux / macOS: `~/.instanseg/`
- `install.bat` and `install.sh` copy `pixi.toml` and `pixi.lock` to the install location before running `pixi install`, ensuring dependency versions are always locked
- Fixed Windows environment detection in Jython: replaced `os.name == "nt"` check (returns `"java"` in Jython) with `os.environ.get("APPDATA")` which is reliable across platforms

### 🗑️ Removed

- `.pixi/` environment folder is no longer created inside `Fiji.app/plugins/InstanSeg/`

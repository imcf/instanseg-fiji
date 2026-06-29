# Changelog

All notable changes to this project will be documented here.

---

## [0.3.0] - 2026-06-29

### ✨ Added

- GitHub Actions release workflow — pushing a `v*` tag now builds and publishes `InstanSeg.zip` automatically with the correct folder name and locked dependencies
- Timestamped log lines in the Fiji Log window via `timed_log()`

### 🔄 Changed

- Python environment is now installed **outside** the Fiji plugins folder to prevent Fiji's script discovery from picking up pixi environment files and cluttering the search results
  - Windows: `C:\Users\<you>\AppData\Roaming\InstanSeg\`
  - Linux / macOS: `~/.instanseg/`
- `install.bat` and `install.sh` copy `pixi.toml` and `pixi.lock` to the install location before running `pixi install`, ensuring dependency versions are always locked
- Fixed Windows environment detection in Jython: replaced `os.name == "nt"` check (returns `"java"` in Jython) with `os.environ.get("APPDATA")` which is reliable across platforms

### 🗑️ Removed

- `.pixi/` environment folder is no longer created inside `Fiji.app/plugins/InstanSeg/`

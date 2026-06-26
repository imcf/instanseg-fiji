# InstanSeg Fiji Plugin

A thin wrapper around [InstanSeg](https://github.com/instanseg) (Goldsborough et al., 2024) that makes the model runnable directly from the Fiji GUI. The Jython plugin (`run_instanseg_fiji.py`) collects parameters from a dialog, then calls a standalone Python subprocess (`_instanseg_runner.py`) that runs inference using the InstanSeg environment and writes label TIFFs back to your results folder. Fiji then opens the labels, converts them to ROIs via MorphoLibJ, and shows them in the ROI Manager.

---

This plugin was developed by Rohan Girish (r.rohangirish@unibas.ch) at the Imaging Core Facility (IMCF) of the University of Basel.

---

## Requirements

### Fiji update sites

Open **Help → Update… → Manage update sites** and make sure the following are enabled:

| Name | URL |
| --- | --- |
| IJPB-plugins (MorphoLibJ) | `https://sites.imagej.net/IJPB-plugins/` |

After enabling the MorphoLibJ site, click **Apply changes** and restart Fiji.

### Pixi (Python environment manager)

The plugin uses [pixi](https://prefix.dev/) to manage a self-contained Python environment with InstanSeg and all its dependencies. Install pixi once on your system:

- **Windows** (PowerShell): `iwr -useb https://pixi.sh/install.ps1 | iex`
- **Linux / macOS**: `curl -fsSL https://pixi.sh/install.sh | bash`

---

## Installation

1. **Download and extract the ZIP.** You will get an `InstanSeg/` folder. Move the entire folder into Fiji's `plugins/` directory so the result looks like this:

   ```text
   Fiji.app/
   └── plugins/
       └── InstanSeg/
           ├── run_instanseg_fiji.py
           ├── _instanseg_runner.py
           ├── pixi.toml
           ├── install.sh
           └── install.bat
   ```

   > On **Windows**, `Fiji.app` is wherever you extracted Fiji — commonly `C:\Tools\Fiji.app` or your desktop. Navigate there, open `plugins\`, and paste the `InstanSeg\` folder in.

2. **Install the Python environment.**

   - **Windows**: open the `InstanSeg\` folder in File Explorer and **double-click `install.bat`**. A terminal window will open and download all dependencies automatically.
   - **Linux / macOS**: open a terminal in the `InstanSeg/` folder and run `bash install.sh`.

   This runs `pixi install`, which downloads Python 3.11, PyTorch, InstanSeg, Bio-Formats, and all other dependencies into a `.pixi/` subfolder inside `InstanSeg/`. It may take several minutes on the first run. You only need to do this once.

3. **Restart Fiji.** The plugin will appear under **Plugins → InstanSeg → run instanseg fiji**.

---

## Usage

1. Go to **Plugins → InstanSeg → Run Instanseg Fiji**.
2. Fill in the dialog:

| Parameter | Description |
| --- | --- |
| **Image path** | Path to the input image (any format supported by Bio-Formats: `.tif`, `.nd2`, `.czi`, `.lif`, …) |
| **Results folder** | Folder where label TIFFs and `RoiSet.zip` will be saved |
| **Model** | `fluorescence_nuclei_and_cells` for fluorescence images; `brightfield_nuclei` for brightfield |
| **Pixel size (µm/px)** | Leave at `0` to read automatically from image metadata (recommended). Override only if the metadata is missing or wrong. |
| **Nuclei channel** | 1-based channel index of the nuclear marker (e.g. DAPI). Set to `0` to skip nuclei output. |
| **Cells channel** | 1-based channel index of the cell body/membrane marker. Set to `0` to skip cell output. Set equal to Nuclei channel to use the same channel for both. |
| **Z-slice** | `0` = max-project across all Z-slices (default). Any other value selects that specific Z-slice (1-based). |
| **Device** | `cpu` (always works), `cuda` (NVIDIA GPU), or `mps` (Apple Silicon). CUDA requires a compatible GPU and the CUDA 11.8 toolkit. |
| **Environment path** | Leave blank to use the bundled pixi environment. Set to the root of a custom conda/pixi environment if you want to use your own. |

1. Click **OK**. Progress is shown in the **Fiji Log** window. After inference:
   - The input image is opened in Fiji.
   - Label images (`_nuclei_labels.tif`, `_cell_labels.tif`) are saved to the results folder and opened with a 16-colour LUT.
   - ROIs are added to the **ROI Manager** (named `nucleus_roi_1`, `nucleus_roi_2`, … / `cell_roi_1`, …).
   - A `<imagename>_RoiSet.zip` is saved to the results folder.

---

## Notes on channel setup

- **Single-channel input, both outputs** (nuclei_ch = cells_ch = 1): the model runs once on channel 1 and returns both nuclei and whole-cell labels from that single stain.
- **Two-channel input** (nuclei_ch = 1, cells_ch = 2): channel 1 (e.g. DAPI) and channel 2 (e.g. WGA/cell membrane) are stacked and passed together. The `fluorescence_nuclei_and_cells` model is specifically trained for this two-channel mode and will give better cell boundary detection.
- **Nuclei only** (cells_ch = 0): only nuclei labels are returned.
- **Cells only** (nuclei_ch = 0): only cell labels are returned.

---

## Citation

If you use this plugin, please cite the original InstanSeg paper:

> Goldsborough, T. et al. (2024). *InstanSeg: an embedding-based instance segmentation algorithm optimized for accurate, efficient and portable cell segmentation.* [arXiv:2408.15954](https://arxiv.org/abs/2408.15954)

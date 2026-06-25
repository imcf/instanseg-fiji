# @ String (visibility=MESSAGE, value="<html><b> Fiji plugin for InstanSeg</b></html>") msg1
# @ String(label="Image path", style="directory", value="") image_path
# @ File(label="Results folder", style="directory") results_dir
# @ String(label="Model", value="fluorescence_nuclei_and_cells", choices={"fluorescence_nuclei_and_cells", "brightfield_nuclei"}) model_type
# @ Double(label="Pixel size (um/px, 0 = read from metadata)", value=0.0) pixel_size
# @ Integer(label="Nuclei channel (1-based, 0 = skip)", value=1) nuclei_channel
# @ Integer(label="Cells channel (1-based, 0 = skip)", value=1) cells_channel
# @ Integer(label="Z-slice (1-based, 0 = max projection)", value=0) seg_z_slice
# @ String(label="Device", value="cpu", choices={"cpu", "cuda", "mps"}) device
# @ String(label="Environment path (leave blank for bundled pixi env)", value="") env_path_override

"""
InstanSeg segmentation plugin for Fiji.

Calls the instanseg_runner.py helper using the Python executable from the pixi environment
bundled alongside this script. Run install.sh (Linux/Mac) or install.bat (Windows) once
before using this plugin to set up the environment.

Place the entire InstanSeg/ folder in:
  Fiji.app/plugins/InstanSeg/
"""

import os
import tempfile

from ij import IJ
from java.lang import ProcessBuilder
from java.io import BufferedReader, InputStreamReader

# Renew SciJava parameter variables to suppress Jython name warnings
image_path = str(image_path).strip()
results_dir = str(results_dir.getAbsolutePath()).strip() if results_dir else ""
pixel_size = float(pixel_size)
model_type = str(model_type)
nuclei_channel = int(nuclei_channel)
cells_channel = int(cells_channel)
seg_z_slice = int(seg_z_slice)
device = str(device)
env_path_override = str(env_path_override).strip()


def find_python(env_root):
    for candidate in [
        os.path.join(env_root, "bin", "python"),
        os.path.join(env_root, "bin", "python3"),
        os.path.join(env_root, "Scripts", "python.exe"),
        os.path.join(env_root, "python.exe"),
    ]:
        if os.path.isfile(candidate):
            return candidate
    return None


def find_pixi_python(script_dir):
    pixi_env = os.path.join(script_dir, ".pixi", "envs", "default")
    return find_python(pixi_env)


def open_label_with_rois(path, title, roi_prefix):
    """Open a label TIFF, apply a colour LUT, and convert labels to ROIs via MorphoLibJ."""
    from ij.plugin.frame import RoiManager

    label_imp = IJ.openImage(path)
    if label_imp is None:
        IJ.log("InstanSeg: WARNING - could not open " + path)
        return
    label_imp.setTitle(title)
    IJ.run(label_imp, "16 colors", "")
    label_imp.show()

    rm = RoiManager.getInstance()
    count_before = rm.getCount() if rm is not None else 0

    try:
        IJ.run(label_imp, "Label image to ROIs", "")
    except Exception as e:
        IJ.log("InstanSeg: MorphoLibJ not available, skipping ROI conversion (" + str(e) + ")")
        print("MorphoLibJ error: " + str(e))
        return

    rm = RoiManager.getInstance()
    if rm is None:
        return
    count_after = rm.getCount()
    for i in range(count_before, count_after):
        rm.getRoi(i).setName(roi_prefix + "_roi_" + str(i - count_before + 1))
    IJ.log("InstanSeg: {} {} ROIs added to ROI Manager".format(
        count_after - count_before, roi_prefix))
    label_imp.hide()

def main():
    if nuclei_channel == 0 and cells_channel == 0:
        IJ.error("InstanSeg", "Both nuclei and cells channels are set to 0.\nSet at least one to a valid channel.")
        raise SystemExit("Nothing to segment")

    script_dir = os.path.join(IJ.getDirectory("plugins"), "InstanSeg")
    runner_path = os.path.join(script_dir, "instanseg_runner.py")

    if not os.path.isfile(runner_path):
        IJ.error("InstanSeg", "Cannot find instanseg_runner.py.\nExpected: " + runner_path)
        raise SystemExit("instanseg_runner.py not found")

    # --- Resolve Python executable ---
    if env_path_override:
        python_path = find_python(env_path_override)
        if python_path is None:
            IJ.error("InstanSeg", "No Python executable found in:\n" + env_path_override)
            raise SystemExit("Python not found in provided environment")
    else:
        python_path = find_pixi_python(script_dir)
        if python_path is None:
            IJ.error(
                "InstanSeg",
                "No Python executable found in the bundled pixi environment.\n"
                "Please run install.sh / install.bat from the InstanSeg plugin folder first.\n"
                "Expected env at: " + os.path.join(script_dir, ".pixi", "envs", "default"),
            )
            raise SystemExit("Python not found in pixi environment")

    print("python: " + python_path)
    print("runner: " + runner_path)

    # --- Open the image in Fiji ---
    IJ.log("InstanSeg: opening " + os.path.basename(image_path))
    imp = IJ.openImage(image_path)
    if imp is None:
        IJ.error("InstanSeg", "Could not open image:\n" + image_path)
        raise SystemExit("Could not open image")
    imp.show()

    # --- Resolve pixel size ---
    # Priority: dialog value > Fiji calibration > let the runner read from metadata
    effective_pixel_size = pixel_size
    if effective_pixel_size == 0.0:
        cal = imp.getCalibration()
        unit = cal.getUnit().lower() if cal.getUnit() else ""
        if cal.scaled() and unit in ("um", u"µm", "micron", "microns"):
            effective_pixel_size = cal.pixelWidth
            print("pixel size from Fiji calibration: {} um/px".format(effective_pixel_size))

    # --- Resolve output directory ---
    if results_dir:
        output_dir = results_dir
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
    else:
        output_dir = tempfile.mkdtemp(prefix="instanseg_")
        IJ.log("InstanSeg: no results folder set, using temp dir: " + output_dir)

    # --- Build subprocess command ---
    cmd = [
        python_path, "-u", runner_path,
        "--image", image_path,
        "--output-dir", output_dir,
        "--model", model_type,
        "--nuclei-channel", str(nuclei_channel),
        "--cells-channel", str(cells_channel),
        "--z-slice", str(seg_z_slice),
        "--device", device,
    ]
    if effective_pixel_size > 0.0:
        cmd += ["--pixel-size", str(effective_pixel_size)]

    print("cmd: " + " ".join(cmd))
    IJ.log("InstanSeg: running inference  [model={}, device={}, nuclei_ch={}, cells_ch={}]".format(
        model_type, device, nuclei_channel, cells_channel))

    # --- Launch subprocess ---
    from java.util import ArrayList
    cmd_list = ArrayList()
    for arg in cmd:
        cmd_list.add(arg)

    pb = ProcessBuilder(cmd_list)
    pb.redirectErrorStream(True)

    # Prepend pixi env DLL directories so the correct native library versions are
    # found before any system DLLs the moment python.exe starts (Windows).
    env_root = os.path.dirname(python_path)
    pb_env = pb.environment()
    current_path = pb_env.get("PATH") or ""
    pixi_paths = [
        os.path.join(env_root, "Library", "bin"),
        os.path.join(env_root, "Library", "mingw-w64", "bin"),
        os.path.join(env_root, "Library", "usr", "bin"),
        env_root,
    ]
    prepend = os.pathsep.join(p for p in pixi_paths if os.path.isdir(p))
    pb_env.put("PATH", prepend + os.pathsep + current_path)

    try:
        process = pb.start()
    except Exception as e:
        IJ.error("InstanSeg", "Failed to start Python process:\n" + str(e))
        raise SystemExit("Process start failed")

    # --- Stream output: INFO: lines -> Fiji Log, everything else -> console ---
    reader = BufferedReader(InputStreamReader(process.getInputStream(), "UTF-8"))
    output_lines = []
    line = reader.readLine()
    while line is not None:
        if line.startswith("INFO:"):
            IJ.log("InstanSeg: " + line[5:])
        elif not (line.startswith("NUCLEI_LABELS:") or line.startswith("CELL_LABELS:")):
            print(line)
        output_lines.append(line)
        line = reader.readLine()
    exit_code = process.waitFor()

    if exit_code != 0:
        print("FAILED with exit code: {} (0x{:08X})".format(exit_code, exit_code & 0xFFFFFFFF))
        raise SystemExit("Runner failed (exit code {})".format(exit_code))

    # --- Parse label paths from runner output ---
    nuclei_path = None
    cells_path = None
    for line in output_lines:
        if line.startswith("NUCLEI_LABELS:"):
            nuclei_path = line[len("NUCLEI_LABELS:"):]
        elif line.startswith("CELL_LABELS:"):
            cells_path = line[len("CELL_LABELS:"):]

    if not nuclei_path and not cells_path:
        IJ.error("InstanSeg", "No label images returned.\nCheck the Script Editor console.")
        raise SystemExit("No labels returned")

    # --- Open labels and convert to ROIs ---
    if nuclei_path:
        open_label_with_rois(nuclei_path, "Nuclei labels", "nucleus")
    if cells_path:
        open_label_with_rois(cells_path, "Cell labels", "cell")

    from ij.plugin.frame import RoiManager
    rm = RoiManager.getInstance()
    if rm is not None:
        rm.setVisible(True)
        if rm.getCount() > 0:
            base = os.path.splitext(os.path.basename(image_path))[0]
            roi_zip = os.path.join(output_dir, base + "_RoiSet.zip")
            rm.runCommand("Deselect")
            rm.runCommand("Save", roi_zip)
            IJ.log("InstanSeg: ROIs saved to " + roi_zip)

    IJ.log("InstanSeg: finished.")


if __name__ == "__main__":
    main()

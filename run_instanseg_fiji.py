# @ String (visibility=MESSAGE, value="<html><b> Fiji plugin for InstanSeg</b></html>") msg1
# @ String(label="Image path", style="open", value="") image_path
# @ String(label="Model", value="fluorescence_nuclei_and_cells", choices={"fluorescence_nuclei_and_cells", "brightfield_nuclei"}) model_type
# @ Double(label="Pixel size (um/px, 0 = read from metadata)", value=0.0) pixel_size
# @ Integer(label="Channel (1-based, 0 = all channels)", value=1) seg_channel
# @ Integer(label="Z-slice (1-based, 0 = max projection)", value=0) seg_z_slice
# @ String(label="Device", value="cpu", choices={"cpu", "cuda", "mps"}) device
# @ String(label="Output labels", value="nuclei_and_cells", choices={"nuclei_and_cells", "nuclei_only", "cells_only"}) output_type
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
pixel_size = float(pixel_size)
model_type = str(model_type)
seg_channel = int(seg_channel)
seg_z_slice = int(seg_z_slice)
device = str(device)
output_type = str(output_type)
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
        IJ.log(
            "InstanSeg: MorphoLibJ not available, skipping ROI conversion ("
            + str(e)
            + ")"
        )
        print("MorphoLibJ error: " + str(e))
        return

    rm = RoiManager.getInstance()
    if rm is None:
        return
    count_after = rm.getCount()
    for i in range(count_before, count_after):
        rm.getRoi(i).setName(roi_prefix + "_" + str(i - count_before + 1))
    IJ.log(
        "InstanSeg: {} {} ROIs added to ROI Manager".format(
            count_after - count_before, roi_prefix
        )
    )


def main():
    script_dir = os.path.join(IJ.getDirectory("plugins"), "InstanSeg")
    runner_path = os.path.join(script_dir, "instanseg_runner.py")

    if not os.path.isfile(runner_path):
        IJ.error(
            "InstanSeg", "Cannot find instanseg_runner.py.\nExpected: " + runner_path
        )
        raise SystemExit("instanseg_runner.py not found")

    # --- Resolve Python executable ---
    if env_path_override:
        python_path = find_python(env_path_override)
        if python_path is None:
            IJ.error(
                "InstanSeg", "No Python executable found in:\n" + env_path_override
            )
            raise SystemExit("Python not found in provided environment")
    else:
        python_path = find_pixi_python(script_dir)
        if python_path is None:
            IJ.error(
                "InstanSeg",
                "No Python executable found in the bundled pixi environment.\n"
                "Please run install.sh / install.bat from the InstanSeg plugin folder first.\n"
                "Expected env at: "
                + os.path.join(script_dir, ".pixi", "envs", "default"),
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
        if cal.scaled() and unit in ("um", "µm", "micron", "microns"):
            effective_pixel_size = cal.pixelWidth
            print(
                "pixel size from Fiji calibration: {} um/px".format(
                    effective_pixel_size
                )
            )

    # --- Build subprocess command ---
    tmp_dir = tempfile.mkdtemp(prefix="instanseg_")
    cmd = [
        python_path,
        "-u",
        runner_path,
        "--image",
        image_path,
        "--output-dir",
        tmp_dir,
        "--model",
        model_type,
        "--channel",
        str(seg_channel),
        "--z-slice",
        str(seg_z_slice),
        "--device",
        device,
    ]

    if pixel_size > 0.0:
        cmd += ["--pixel-size", str(pixel_size)]

    IJ.log("InstanSeg: running inference...")
    IJ.log("InstanSeg: cmd -> " + " ".join(cmd))

    from java.util import ArrayList

    cmd_list = ArrayList()
    for arg in cmd:
        cmd_list.add(arg)
    pb = ProcessBuilder(cmd_list)
    pb.redirectErrorStream(True)  # merge stderr into stdout

    # Prepend the pixi env's DLL directories to PATH so the correct runtime versions
    # are found before any system DLLs from the moment python.exe starts.
    env_root = os.path.dirname(python_path)
    pixi_paths = [
        os.path.join(env_root, "Library", "bin"),
        os.path.join(env_root, "Library", "mingw-w64", "bin"),
        os.path.join(env_root, "Library", "usr", "bin"),
        env_root,
    ]
    pb_env = pb.environment()
    current_path = pb_env.get("PATH") or ""
    prepend = os.pathsep.join(p for p in pixi_paths if os.path.isdir(p))
    pb_env.put("PATH", prepend + os.pathsep + current_path)
    try:
        process = pb.start()
    except Exception as e:
        IJ.error(
            "InstanSeg",
            "Failed to start Python process:\n"
            + str(e)
            + "\nPython path: "
            + python_path,
        )
        raise SystemExit("Process start failed")

    reader = BufferedReader(InputStreamReader(process.getInputStream(), "UTF-8"))
    output_lines = []
    line = reader.readLine()
    while line is not None:
        print("[runner] " + line)
        output_lines.append(line)
        line = reader.readLine()
    exit_code = process.waitFor()

    if exit_code != 0:
        print(
            "[runner] FAILED with exit code: "
            + str(exit_code)
            + " (0x{:08X})".format(exit_code & 0xFFFFFFFF)
        )
        raise SystemExit("Runner failed (exit code " + str(exit_code) + ")")

    # Parse the label file paths printed by the runner
    nuclei_path = None
    cells_path = None
    labels_path = None
    for line in output_lines:
        if line.startswith("NUCLEI_LABELS:"):
            nuclei_path = line[len("NUCLEI_LABELS:") :]
        elif line.startswith("CELL_LABELS:"):
            cells_path = line[len("CELL_LABELS:") :]
        elif line.startswith("LABELS:"):
            labels_path = line[len("LABELS:") :]

    if nuclei_path and cells_path:
        open_label(nuclei_path, "Nuclei labels")
        open_label(cells_path, "Cell labels")
    elif labels_path:
        open_label(labels_path, "Labels")
    else:
        IJ.error(
            "InstanSeg",
            "No label images returned.\nCheck the Script Editor console for details.",
        )

    print("InstanSeg: done.")


if __name__ == "__main__":
    main()

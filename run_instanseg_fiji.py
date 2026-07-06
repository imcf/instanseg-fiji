# @ String (visibility=MESSAGE, value="<html><b> Fiji plugin for InstanSeg</b></html>") msg1
# @ File(label="Image path", style="open") image_path
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

Runs the _instanseg_runner.py helper as an Appose task. Appose builds the pixi
environment itself from the pixi.toml bundled alongside this script, the first
time the plugin is used, and reuses it on every later run.

Place the entire InstanSeg/ folder in:
  Fiji.app/plugins/
"""

import os
import shutil
import tempfile
import time

from ij import IJ  # pyright: ignore[reportMissingImports]
from ij.plugin.frame import RoiManager  # pyright: ignore[reportMissingImports]
from org.apposed.appose import Appose  # pyright: ignore[reportMissingImports]

# Renew SciJava parameter variables to suppress Jython name warnings
image_path = str(image_path.getAbsolutePath()).strip() if image_path else ""
results_dir = str(results_dir.getAbsolutePath()).strip() if results_dir else ""
pixel_size = float(pixel_size)
model_type = str(model_type)
nuclei_channel = int(nuclei_channel) 
cells_channel = int(cells_channel)
seg_z_slice = int(seg_z_slice)
device = str(device)
env_path_override = str(env_path_override).strip()


def timed_log(message, as_string=False):
    """Print a message to the ImageJ log window, prefixed with a timestamp.

    If `as_string` is set to True, nothing will be printed to the log window,
    instead the formatted log message will be returned as a string.

    Parameters
    ----------
    message : str
        Message to print
    as_string : bool, optional
        Flag to request the formatted string to be returned instead of printing
        it to the log. By default False.
    """
    formatted = time.strftime("%H:%M:%S", time.localtime()) + ": " + message + " "
    if as_string:
        return formatted
    IJ.log(formatted)


def log_worker_debug(message):
    """Forward Appose service/worker debug output to the console.

    Falls back to an ASCII-safe encoding since Windows consoles are often
    stuck on a legacy codepage (e.g. cp850) that can't print every character
    pixi or Python might emit.
    """
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "backslashreplace"))


def log_task_progress(event):
    """Forward Appose task progress messages to the Fiji log window."""
    if event.message:
        timed_log(event.message)


def log_build_progress(title, current, maximum):
    """Forward Appose environment build progress to the Fiji log window."""
    if maximum > 0:
        timed_log("{}: {}/{}".format(title, current, maximum))
    else:
        timed_log(title)


def get_instanseg_env_dir():
    """Return the directory where the InstanSeg pixi environment is expected to be found.
    On Windows, this is %APPDATA%\InstanSeg. On Linux/Mac, this is ~/.instanseg."""
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return os.path.join(appdata, "InstanSeg")
    return os.path.join(os.path.expanduser("~"), ".instanseg")


def open_label_with_rois(path, title, roi_prefix):
    """Open a label TIFF, apply a colour LUT, and convert labels to ROIs via MorphoLibJ."""
    label_imp = IJ.openImage(path)
    if label_imp is None:
        timed_log("WARNING - could not open " + path)
        return
    label_imp.setTitle(title)
    IJ.run(label_imp, "16 colors", "")
    label_imp.show()

    rm = RoiManager.getInstance()
    count_before = rm.getCount() if rm is not None else 0

    try:
        IJ.run(label_imp, "Label image to ROIs", "")
    except Exception as e:
        timed_log("MorphoLibJ not available, skipping ROI conversion (" + str(e) + ")")
        print("MorphoLibJ error: " + str(e))
        return

    rm = RoiManager.getInstance()
    if rm is None:
        return
    count_after = rm.getCount()
    for i in range(count_before, count_after):
        rm.getRoi(i).setName(roi_prefix + "_roi_" + str(i - count_before + 1))
    timed_log(
        "{} {} ROIs added to ROI Manager".format(count_after - count_before, roi_prefix)
    )
    label_imp.hide()


def main():
    if not image_path or not os.path.isfile(image_path):
        IJ.error(
            "InstanSeg", "Image file not found:\n" + (image_path or "<none selected>")
        )
        raise SystemExit("Image not found")

    if nuclei_channel == 0 and cells_channel == 0:
        IJ.error(
            "InstanSeg",
            "Both nuclei and cells channels are set to 0.\nSet at least one to a valid channel.",
        )
        raise SystemExit("Nothing to segment")

    script_dir = os.path.join(IJ.getDirectory("plugins"), "InstanSeg")
    runner_path = os.path.join(script_dir, "_instanseg_runner.py")

    if not os.path.isfile(runner_path):
        IJ.error(
            "InstanSeg", "Cannot find _instanseg_runner.py.\nExpected: " + runner_path
        )
        raise SystemExit("instanseg_runner.py not found")

    # Get the InstanSeg environment, building it with Appose if needed.
    # A custom environment path is just wrapped as-is. The bundled environment
    # is built from pixi.toml the first time, then reused on every later run
    # (Appose skips the rebuild once the environment is already up to date).
    if env_path_override:
        env_dir = env_path_override
        print("environment dir: " + env_dir)
        try:
            env = Appose.wrap(env_dir)
        except Exception as e:
            IJ.error(
                "InstanSeg", "Could not use environment at:\n" + env_dir + "\n\n" + str(e)
            )
            raise SystemExit("Environment not usable")
    else:
        env_dir = get_instanseg_env_dir()
        pixi_toml_path = os.path.join(script_dir, "pixi.toml")
        pixi_lock_path = os.path.join(script_dir, "pixi.lock")

        if not os.path.isfile(pixi_toml_path):
            IJ.error("InstanSeg", "Cannot find pixi.toml.\nExpected: " + pixi_toml_path)
            raise SystemExit("pixi.toml not found")

        print("environment dir: " + env_dir)
        if not os.path.isdir(env_dir):
            os.makedirs(env_dir)
        if os.path.isfile(pixi_lock_path):
            shutil.copyfile(pixi_lock_path, os.path.join(env_dir, "pixi.lock"))

        timed_log("preparing InstanSeg environment (first run can take a few minutes)...")
        try:
            env = (
                Appose.pixi(pixi_toml_path)
                .base(env_dir)
                .subscribeOutput(log_worker_debug)
                .subscribeError(log_worker_debug)
                .subscribeProgress(log_build_progress)
                .build()
            )
        except Exception as e:
            IJ.error("InstanSeg", "Could not build environment at:\n" + env_dir + "\n\n" + str(e))
            raise SystemExit("Environment build failed")

    # Open the image in Fiji
    timed_log("opening " + os.path.basename(image_path))
    imp = IJ.openImage(image_path)
    if imp is None:
        IJ.error("InstanSeg", "Could not open image:\n" + image_path)
        raise SystemExit("Could not open image")
    imp.show()

    # Resolve effective pixel size
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

    # Resolve output directory
    if results_dir:
        output_dir = results_dir
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir)
    else:
        output_dir = tempfile.mkdtemp(prefix="instanseg_")
        timed_log("no results folder set, using temp dir: " + output_dir)

    # Init script: heavy imports (numpy, torch, and anything that starts a JVM
    # like bioio_bioformats) must happen before the worker opens stdin for the
    # task protocol, or they can hang on Windows. See apposed/appose#23.
    # Everything imported here also becomes available as a global inside every
    # task script, so run_instanseg is ready to call directly below.
    init_script = (
        "import os\n"
        "os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'\n"
        "import sys\n"
        "sys.path.insert(0, {plugin_dir!r})\n"
        "import numpy\n"
        "import torch\n"
        "import tifffile\n"
        "import bioio_bioformats\n"
        "import scyjava\n"
        "scyjava.start_jvm()\n"
        "from instanseg import InstanSeg\n"
        "from _instanseg_runner import run_instanseg\n"
    ).format(plugin_dir=script_dir)

    # Build the Appose task
    # run_instanseg() was already imported by the init script above, so the
    # task script just calls it. Its return value (a dict) becomes the task's outputs.
    worker_script = (
        "run_instanseg(\n"
        "    image=image,\n"
        "    output_dir=output_dir,\n"
        "    model=model,\n"
        "    nuclei_channel=nuclei_channel,\n"
        "    cells_channel=cells_channel,\n"
        "    z_slice=z_slice,\n"
        "    device=device,\n"
        "    pixel_size=pixel_size,\n"
        "    task=task,\n"
        ")\n"
    )

    inputs = {
        "image": image_path,
        "output_dir": output_dir,
        "model": model_type,
        "nuclei_channel": nuclei_channel,
        "cells_channel": cells_channel,
        "z_slice": seg_z_slice,
        "device": device,
        "pixel_size": effective_pixel_size if effective_pixel_size > 0.0 else None,
    }

    timed_log(
        "running inference  [model={}, device={}, nuclei_ch={}, cells_ch={}]".format(
            model_type, device, nuclei_channel, cells_channel
        )
    )

    # Launch the worker process and run the task
    service = env.python()
    service.init(init_script)
    service.debug(log_worker_debug)

    task = service.task(worker_script, inputs)
    task.listen(log_task_progress)

    try:
        task.waitFor()
    except Exception as e:
        IJ.error("InstanSeg", "Inference failed:\n" + str(e))
        raise SystemExit("Runner failed")

    # Read label paths from the task outputs
    nuclei_path = task.outputs.get("nuclei_path")
    cells_path = task.outputs.get("cells_path")

    if not nuclei_path and not cells_path:
        IJ.error(
            "InstanSeg", "No label images returned.\nCheck the Script Editor console."
        )
        raise SystemExit("No labels returned")

    # Open labels and convert to ROIs
    if nuclei_path:
        open_label_with_rois(nuclei_path, "Nuclei labels", "nucleus")
    if cells_path:
        open_label_with_rois(cells_path, "Cell labels", "cell")

    rm = RoiManager.getInstance()
    if rm is not None:
        rm.setVisible(True)
        if rm.getCount() > 0:
            base = os.path.splitext(os.path.basename(image_path))[0]
            roi_zip = os.path.join(output_dir, base + "_RoiSet.zip")
            rm.runCommand("Deselect")
            rm.runCommand("Save", roi_zip)
            timed_log("ROIs saved to " + roi_zip)

    timed_log("Finished.")


if __name__ == "__main__":
    main()

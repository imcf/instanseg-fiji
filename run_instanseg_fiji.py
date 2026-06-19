#@ String (visibility=MESSAGE, value="<html><b> Fiji plugin for InstanSeg</b></html>") msg1
# @ File(label="Image path", style="open") image_path
# @ File(label="InstanSeg environment path", style="directory", description="Root of the conda/pixi env that has instanseg installed") env_path
# @ String(label="Model", value="fluorescence_nuclei_and_cells", choices={"fluorescence_nuclei_and_cells", "brightfield_nuclei"}) model_type
# @ Double(label="Pixel size (um/px, 0 = read from metadata)", value=0.0) pixel_size

"""
InstanSeg segmentation plugin for Fiji.

Calls the instanseg_runner.py helper using the Python executable found in the environment path
provided by the user through conda or pixi. This script writes label TIFFs to a temp directory,
then opens them alongside the original image in Fiji.

Place both this file and instanseg_runner.py in:
  Fiji.app/scripts/Plugins/InstanSeg/
"""

import os
import sys
import subprocess
import tempfile

from ij import IJ
from ij.plugin import LUT

# To ignore Code warnings, we renew the variables
image_path = image_path.getAbsolutePath()
env_path   = env_path.getAbsolutePath()
pixel_size = pixel_size
model_type = model_type


# Find the python executable in the given env.
def find_python(env_root):
    """Find the Python executable in the given environment root directory, going through 
    a list of candidates.

    Parameters
    ----------
        env_root (str): The root directory of the environment.
    """
    
    candidate_paths = [
        os.path.join(env_root, "bin", "python"), # conda/pixi Linux & Mac
        os.path.join(env_root, "bin", "python3"), 
        os.path.join(env_root, "python.exe"),  # Windows FIXME
    ]
    for c in candidate_paths:
        if os.path.isfile(c):
            return c
    return None


def open_label(path, title):
    label_imp = IJ.openImage(path)
    if label_imp is None:
        IJ.log("InstanSeg: WARNING - could not open " + path)
        return
    label_imp.setTitle(title)
    IJ.run(label_imp, "16 colors", "")
    label_imp.show()


def main():
    # Locate the runner script next to this file
    script_dir  = os.path.dirname(os.path.abspath(__file__))
    runner_path = os.path.join(script_dir, "instanseg_runner.py")

    if not os.path.isfile(runner_path):
        IJ.error("InstanSeg", "Cannot find instanseg_runner.py next to this script.\nExpected: " + runner_path)
        raise SystemExit("instanseg_runner.py not found")

    # Find python executable
    python_path = find_python(env_path)
    if python_path is None:
        IJ.error("InstanSeg", "No Python executable found in:\n" + env_path)
        raise SystemExit("Python not found in environment")
    IJ.log("InstanSeg: using Python at " + python_path)

    # Open the original image in Fiji
    IJ.log("InstanSeg: opening image: " + image_path)
    imp = IJ.openImage(image_path)
    if imp is None:
        IJ.error("InstanSeg", "Could not open image:\n" + image_path)
        raise SystemExit("Could not open image")
    imp.show()

    # Create a temp directory for the label TIFFs
    tmp_dir = tempfile.mkdtemp(prefix="instanseg_")
    IJ.log("InstanSeg: output dir -> " + tmp_dir)

    # Build the subprocess command
    cmd = [python_path, runner_path,
           "--image",      image_path,
           "--output-dir", tmp_dir,
           "--model",      model_type]
    if pixel_size > 0.0:
        cmd += ["--pixel-size", str(pixel_size)]

    IJ.log("InstanSeg: running inference (this may take a while)...")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_bytes, stderr_bytes = proc.communicate()

    # Mirror runner output to the Fiji log
    stdout_str = stdout_bytes.decode("utf-8")
    for line in stdout_str.splitlines():
        IJ.log("  [runner] " + line)
    for line in stderr_bytes.decode("utf-8").splitlines():
        IJ.log("  [runner ERR] " + line)

    if proc.returncode != 0:
        IJ.error("InstanSeg", "Inference failed (exit code " + str(proc.returncode) + ").\nCheck the Fiji log for details.")
        raise SystemExit("Runner failed")

    # Parse the label file paths printed by the runner
    nuclei_path = None
    cells_path  = None
    labels_path = None

    # We could go by the file name after saving, but we can grab the stdout directly
    for line in stdout_str.splitlines():
        if line.startswith("NUCLEI_LABELS:"):
            nuclei_path = line[len("NUCLEI_LABELS:"):]
        elif line.startswith("CELL_LABELS:"):
            cells_path = line[len("CELL_LABELS:"):]
        elif line.startswith("LABELS:"):
            labels_path = line[len("LABELS:"):]

    # Open label images
    if nuclei_path and cells_path:
        open_label(nuclei_path, "Nuclei labels")
        open_label(cells_path,  "Cell labels")
    elif labels_path:
        open_label(labels_path, "Labels")
    else:
        IJ.error("InstanSeg", "No label images returned.\nCheck the Fiji log for details.")

    IJ.log("InstanSeg: done.")


main()


# @ String (visibility=MESSAGE, value="<html><b> Fiji plugin for InstanSeg</b></html>") msg1
# @ String(label="Image path", style="open", value="") image_path
# @ String(label="Model", value="fluorescence_nuclei_and_cells", choices={"fluorescence_nuclei_and_cells", "brightfield_nuclei"}) model_type
# @ Double(label="Pixel size (um/px, 0 = read from metadata)", value=0.0) pixel_size
# @ Integer(label="Channel (1-based, 0 = all channels)", value=1) seg_channel
# @ Integer(label="Z-slice (1-based, 0 = max projection)", value=0) seg_z_slice
# @ String(label="Device", value="cpu", choices={"cpu", "cuda", "mps"}) device
# @ String(label="Environment path (leave blank for bundled pixi env)", value="") env_path_override

"""
InstanSeg segmentation plugin for Fiji.

Calls the instanseg_runner.py helper using the Python executable from the pixi environment
bundled alongside this script. Run install.sh (Linux/Mac) or install.bat (Windows) once
before using this plugin to set up the environment.

Place the entire InstanSeg/ folder in:
  Fiji.app/scripts/Plugins/
"""

import os
import tempfile

from ij import IJ
from java.lang import ProcessBuilder
from java.io import BufferedReader, InputStreamReader

# To ignore Code warnings, we renew the variables
image_path = str(image_path).strip()
pixel_size = pixel_size
model_type = model_type
seg_channel = seg_channel
seg_z_slice = seg_z_slice
device = str(device)
env_path_override = env_path_override.strip()


def find_python(env_root):
    """Find the Python executable in the given environment root directory."""
    candidate_paths = [
        os.path.join(env_root, "bin", "python"),  # pixi/conda Linux & Mac
        os.path.join(env_root, "bin", "python3"),
        os.path.join(env_root, "Scripts", "python.exe"),  # pixi Windows
        os.path.join(env_root, "python.exe"),
    ]
    for c in candidate_paths:
        if os.path.isfile(c):
            return c
    return None


def find_pixi_python(script_dir):
    """Locate the Python bundled in the pixi env next to this script."""
    pixi_env = os.path.join(script_dir, ".pixi", "envs", "default")
    return find_python(pixi_env)


def open_label(path, title):
    label_imp = IJ.openImage(path)
    if label_imp is None:
        IJ.log("InstanSeg: WARNING - could not open " + path)
        return
    label_imp.setTitle(title)
    IJ.run(label_imp, "16 colors", "")
    label_imp.show()


def main():
    # Scripts are always at <Fiji.app>/scripts/Plugins/InstanSeg/
    # script_dir = os.path.join(
    #     IJ.getDirectory("fiji"), "scripts", "Plugins", "InstanSeg"
    # )
    # runner_path = os.path.join(script_dir, "instanseg_runner.py")

    runner_path = (
        r"C:\Tools\Fiji.app-2025-05-06\scripts\Plugins\InstanSeg\instanseg_runner.py"
    )
    script_dir = os.path.dirname(runner_path)
    IJ.log("InstanSeg: runner path -> " + runner_path)

    if not os.path.isfile(runner_path):
        IJ.error(
            "InstanSeg", "Cannot find instanseg_runner.py.\nExpected: " + runner_path
        )
        raise SystemExit("instanseg_runner.py not found")

    # Find python executable — explicit override takes priority, else use bundled pixi env
    if env_path_override:
        python_path = find_python(env_path_override)
        if python_path is None:
            IJ.error(
                "InstanSeg",
                "No Python executable found in the provided path:\n"
                + env_path_override,
            )
            raise SystemExit("Python not found in provided environment")
        IJ.log("InstanSeg: using Python at " + python_path + " (from override)")
    else:
        python_path = find_pixi_python(script_dir)
        if python_path is None:
            IJ.error(
                "InstanSeg",
                "No Python executable found in the bundled pixi environment.\n"
                "Please run install.sh (Linux/Mac) or install.bat (Windows)\n"
                "from the InstanSeg plugin folder first.\n"
                "Expected env at: "
                + os.path.join(script_dir, ".pixi", "envs", "default"),
            )
            raise SystemExit("Python not found in pixi environment")
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
    cmd = [
        python_path,
        "-u",          # unbuffered stdout/stderr — ensures output reaches the pipe
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

    # Use Java ProcessBuilder — more reliable than Jython subprocess on Windows
    from java.util import ArrayList
    cmd_list = ArrayList()
    for arg in cmd:
        cmd_list.add(arg)
    pb = ProcessBuilder(cmd_list)
    pb.redirectErrorStream(True)  # merge stderr into stdout
    try:
        process = pb.start()
    except Exception as e:
        IJ.error("InstanSeg", "Failed to start Python process:\n" + str(e) +
                 "\nPython path: " + python_path)
        raise SystemExit("Process start failed")

    reader = BufferedReader(InputStreamReader(process.getInputStream(), "UTF-8"))
    output_lines = []
    line = reader.readLine()
    while line is not None:
        IJ.log("  [runner] " + line)
        output_lines.append(line)
        line = reader.readLine()
    exit_code = process.waitFor()

    if exit_code != 0:
        IJ.error(
            "InstanSeg",
            "Inference failed (exit code "
            + str(exit_code)
            + ").\nCheck the Fiji log for details.",
        )
        raise SystemExit("Runner failed")

    stdout_str = "\n".join(output_lines)

    # Parse the label file paths printed by the runner
    nuclei_path = None
    cells_path = None
    labels_path = None

    # We could go by the file name after saving, but we can grab the stdout directly
    for line in stdout_str.splitlines():
        if line.startswith("NUCLEI_LABELS:"):
            nuclei_path = line[len("NUCLEI_LABELS:") :]
        elif line.startswith("CELL_LABELS:"):
            cells_path = line[len("CELL_LABELS:") :]
        elif line.startswith("LABELS:"):
            labels_path = line[len("LABELS:") :]

    # Open label images
    if nuclei_path and cells_path:
        open_label(nuclei_path, "Nuclei labels")
        open_label(cells_path, "Cell labels")
    elif labels_path:
        open_label(labels_path, "Labels")
    else:
        IJ.error(
            "InstanSeg", "No label images returned.\nCheck the Fiji log for details."
        )

    IJ.log("InstanSeg: done.")


if __name__ == "__main__":
    main()

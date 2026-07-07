"""
InstanSeg inference helper script.

Called from the Fiji Jython plugin (run_instanseg_fiji.py) as an Appose task,
running inside the InstanSeg pixi environment. Can also be run standalone from
the command line for testing:

    python _instanseg_runner.py --image /path/to/image.tif \
                               --output-dir /tmp/instanseg_out \
                               --model fluorescence_nuclei_and_cells \
                               --nuclei-channel 1 \
                               --cells-channel 2 \
                               --z-slice 0 \
                               --pixel-size 0.5
"""

import os

# Fix OpenMP conflict between PyTorch and numpy on Windows (libiomp5md.dll vs libomp.dll)
# Must be set before torch/numpy are imported
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def _notify(task, message):
    """Send a progress message. Routed through Appose when a task is given,
    otherwise just printed (standalone CLI use)."""
    if task is not None:
        task.update(message=message)
    else:
        print(message)


def _prepare_input(image_path, nuclei_ch, cells_ch, z_slice=0):
    """Read image and build the array to pass to InstanSeg.

    - nuclei_ch / cells_ch: 1-based channel indices. 0 means skip that output.
    - If both are the same non-zero value: one channel -> (H, W).
    - If they differ and both non-zero: stack them -> (2, H, W) so InstanSeg can
      use both (nuclear marker + cell marker) simultaneously.
    - If only one is non-zero: single channel -> (H, W).

    Returns (image_array, pixel_size_um).
    """
    import numpy as np
    from bioio import BioImage
    import bioio_bioformats

    img = BioImage(image_path, reader=bioio_bioformats.Reader)
    pixel_size = img.physical_pixel_sizes.X  # um/px, may be None

    data = img.get_image_data("CZYX")  # (C, Z, Y, X)
    n_channels, n_z = data.shape[0], data.shape[1]

    def extract(ch):
        if ch > n_channels:
            raise ValueError(
                "Channel {} requested but image only has {} channel(s)".format(
                    ch, n_channels
                )
            )
        plane = data[ch - 1]  # (Z, Y, X)
        if z_slice == 0:
            result = plane.max(axis=0)
        else:
            if z_slice > n_z:
                raise ValueError(
                    "Z-slice {} requested but image only has {} Z-slices".format(
                        z_slice, n_z
                    )
                )
            result = plane[z_slice - 1]
        return result  # (H, W)

    slices = []
    if nuclei_ch > 0:
        slices.append(extract(nuclei_ch))
    if cells_ch > 0 and cells_ch != nuclei_ch:
        slices.append(extract(cells_ch))

    if len(slices) == 1:
        return slices[0], pixel_size  # (H, W)
    else:
        return np.stack(slices, axis=0), pixel_size  # (2, H, W)


def run_instanseg(
    image,
    output_dir,
    model="fluorescence_nuclei_and_cells",
    nuclei_channel=1,
    cells_channel=1,
    z_slice=0,
    device="cpu",
    pixel_size=None,
    task=None,
):
    """Run InstanSeg inference on a single image and save label images.

    Returns a dict with the paths and counts of whatever labels were produced.
    Any errors are simply raised - when called as an Appose task, Appose
    reports the exception back to the caller as a task failure automatically.
    """
    import tifffile

    if nuclei_channel == 0 and cells_channel == 0:
        raise ValueError("Both nuclei_channel and cells_channel are 0, nothing to do")

    if device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""

    _notify(task, "Image: " + os.path.basename(image))
    _notify(task, "Model: " + model + "  |  Device: " + device)

    from instanseg import InstanSeg

    os.makedirs(output_dir, exist_ok=True)

    _notify(task, "Loading model...")
    instanseg = InstanSeg(model, verbosity=0, device=device)

    _notify(task, "Reading image...")
    image_array, metadata_pixel_size = _prepare_input(
        image, nuclei_channel, cells_channel, z_slice
    )

    # Pixel size: explicit argument > bioio metadata > warn
    if pixel_size is not None:
        _notify(task, "Pixel size: {} um/px (from dialog)".format(pixel_size))
    elif metadata_pixel_size is not None:
        pixel_size = metadata_pixel_size
        _notify(task, "Pixel size: {} um/px (from metadata)".format(pixel_size))
    else:
        _notify(task, "WARNING: pixel size unknown - proceeding without rescaling")

    _notify(task, "Running inference...")
    instances, _ = instanseg.eval_small_image(image_array, pixel_size)

    n_outputs = instances.shape[1]
    has_nuclei = n_outputs >= 1 and bool(instances[0, 0].any().item())
    has_cells = n_outputs >= 2 and bool(instances[0, 1].any().item())

    save_nuclei = nuclei_channel > 0 and has_nuclei
    save_cells = cells_channel > 0 and has_cells

    if nuclei_channel > 0 and not has_nuclei:
        _notify(task, "WARNING: no nuclei detected in model output")
    if cells_channel > 0 and not has_cells:
        _notify(task, "WARNING: no cells detected in model output")

    if not save_nuclei and not save_cells:
        raise RuntimeError(
            "Nothing to save - check channel settings and model compatibility"
        )

    base = os.path.splitext(os.path.basename(image))[0]
    result = {}

    if save_nuclei:
        n_nuclei = int(instances[0, 0].max().item())
        nuclei_path = os.path.join(output_dir, base + "_nuclei_labels.tif")
        tifffile.imwrite(nuclei_path, instances[0, 0].numpy().astype("uint16"))
        _notify(task, "Nuclei detected: {}".format(n_nuclei))
        result["nuclei_path"] = nuclei_path
        result["n_nuclei"] = n_nuclei

    if save_cells:
        n_cells = int(instances[0, 1].max().item())
        cells_path = os.path.join(output_dir, base + "_cell_labels.tif")
        tifffile.imwrite(cells_path, instances[0, 1].numpy().astype("uint16"))
        _notify(task, "Cells detected: {}".format(n_cells))
        result["cells_path"] = cells_path
        result["n_cells"] = n_cells

    _notify(task, "Done.")
    return result


def _main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run InstanSeg inference on a single image."
    )
    parser.add_argument("--image", required=True)
    parser.add_argument("--output-dir", required=True, dest="output_dir")
    parser.add_argument("--model", default="fluorescence_nuclei_and_cells")
    parser.add_argument("--pixel-size", type=float, default=None, dest="pixel_size")
    parser.add_argument(
        "--nuclei-channel", type=int, default=1, dest="nuclei_channel",
        help="1-based input channel for nuclei. 0 = do not output nuclei labels.",
    )
    parser.add_argument(
        "--cells-channel", type=int, default=1, dest="cells_channel",
        help="1-based input channel for cells. 0 = do not output cell labels.",
    )
    parser.add_argument("--z-slice", type=int, default=0, dest="z_slice")
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()

    result = run_instanseg(
        image=args.image,
        output_dir=args.output_dir,
        model=args.model,
        nuclei_channel=args.nuclei_channel,
        cells_channel=args.cells_channel,
        z_slice=args.z_slice,
        device=args.device,
        pixel_size=args.pixel_size,
    )
    print(result)


if __name__ == "__main__":
    _main()

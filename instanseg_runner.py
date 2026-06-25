"""
InstanSeg inference helper script.
Called by the Fiji Jython plugin via subprocess using the InstanSeg Python environment.

Usage:
    python instanseg_runner.py --image /path/to/image.tif \
                               --output-dir /tmp/instanseg_out \
                               --model fluorescence_nuclei_and_cells \
                               --channel 1 \
                               --z-slice 0 \
                               --pixel-size 0.5
"""

import os

# Fix OpenMP conflict between PyTorch and numpy on Windows (libiomp5md.dll vs libomp.dll)
# Must be set before any library imports
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import sys
import traceback


def info(msg):
    """User-facing message — routed to the Fiji Log by the Jython caller."""
    print("INFO:" + msg)
    sys.stdout.flush()


def debug(msg):
    """Developer/diagnostic message — goes to the Script Editor console."""
    print("[DEBUG] " + msg)
    sys.stdout.flush()


def _prepare_input(image_path, nuclei_ch, cells_ch, z_slice=0):
    """Read image and build the array to pass to InstanSeg.

    - nuclei_ch / cells_ch: 1-based channel indices. 0 means skip that output.
    - If both are the same non-zero value: one channel → (H, W).
    - If they differ and both non-zero: stack them → (2, H, W) so InstanSeg can
      use both (nuclear marker + cell marker) simultaneously.
    - If only one is non-zero: single channel → (H, W).

    Returns (image_array, pixel_size_um).
    """
    import numpy as np
    from bioio import BioImage
    import bioio_bioformats

    img = BioImage(image_path, reader=bioio_bioformats.Reader)
    pixel_size = img.physical_pixel_sizes.X  # µm/px, may be None

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
            debug("Channel {}: max-projecting {} Z-slices".format(ch, n_z))
        else:
            if z_slice > n_z:
                raise ValueError(
                    "Z-slice {} requested but image only has {} Z-slices".format(
                        z_slice, n_z
                    )
                )
            result = plane[z_slice - 1]
            debug("Channel {}: using Z-slice {}".format(ch, z_slice))
        return result  # (H, W)

    slices = []
    if nuclei_ch > 0:
        slices.append(extract(nuclei_ch))
        debug("Nuclei input: channel {}".format(nuclei_ch))
    if cells_ch > 0 and cells_ch != nuclei_ch:
        slices.append(extract(cells_ch))
        debug("Cells input: channel {}".format(cells_ch))

    if len(slices) == 1:
        return slices[0], pixel_size          # (H, W)
    else:
        return np.stack(slices, axis=0), pixel_size  # (2, H, W)


def main():
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

    debug("args: image={} model={} nuclei_ch={} cells_ch={} z_slice={} device={} pixel_size={}".format(
        args.image, args.model, args.nuclei_channel, args.cells_channel,
        args.z_slice, args.device, args.pixel_size))

    if args.nuclei_channel == 0 and args.cells_channel == 0:
        print("ERROR: both --nuclei-channel and --cells-channel are 0, nothing to do")
        sys.exit(1)

    if args.device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        debug("CUDA disabled (cpu mode)")

    info("Image: " + os.path.basename(args.image))
    info("Model: " + args.model + "  |  Device: " + args.device)

    debug("importing instanseg...")
    try:
        from instanseg import InstanSeg
        debug("instanseg OK")
    except Exception:
        print("ERROR: instanseg import failed:\n" + traceback.format_exc())
        sys.exit(1)

    debug("importing tifffile / bioio...")
    try:
        import tifffile
        import bioio_bioformats  # noqa: F401
        debug("imports OK")
    except Exception:
        print("ERROR: import failed:\n" + traceback.format_exc())
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    info("Loading model...")
    try:
        instanseg = InstanSeg(args.model, verbosity=0, device=args.device)
        debug("model loaded OK")
    except Exception:
        print("ERROR: model loading failed:\n" + traceback.format_exc())
        sys.exit(1)

    info("Reading image...")
    try:
        image_array, pixel_size = _prepare_input(
            args.image, args.nuclei_channel, args.cells_channel, args.z_slice
        )
        debug("image shape={} dtype={}".format(image_array.shape, image_array.dtype))
    except Exception:
        print("ERROR: image reading failed:\n" + traceback.format_exc())
        sys.exit(1)

    # Pixel size: CLI arg > bioio metadata > warn
    if args.pixel_size is not None:
        pixel_size = args.pixel_size
        info("Pixel size: {} um/px (from dialog)".format(pixel_size))
    elif pixel_size is not None:
        info("Pixel size: {} um/px (from metadata)".format(pixel_size))
    else:
        info("WARNING: pixel size unknown — proceeding without rescaling")

    info("Running inference...")
    try:
        instances, _ = instanseg.eval_small_image(image_array, pixel_size)
        debug("inference OK, output shape={}".format(instances.shape))
    except Exception:
        print("ERROR: inference failed:\n" + traceback.format_exc())
        sys.exit(1)

    n_outputs = instances.shape[1]
    has_nuclei = n_outputs >= 1 and bool(instances[0, 0].any().item())
    has_cells  = n_outputs >= 2 and bool(instances[0, 1].any().item())

    save_nuclei = args.nuclei_channel > 0 and has_nuclei
    save_cells  = args.cells_channel  > 0 and has_cells

    if args.nuclei_channel > 0 and not has_nuclei:
        info("WARNING: no nuclei detected in model output")
    if args.cells_channel > 0 and not has_cells:
        info("WARNING: no cells detected in model output")

    base = os.path.splitext(os.path.basename(args.image))[0]

    if save_nuclei:
        n_nuclei = int(instances[0, 0].max().item())
        nuclei_path = os.path.join(args.output_dir, base + "_nuclei_labels.tif")
        tifffile.imwrite(nuclei_path, instances[0, 0].numpy().astype("uint16"))
        info("Nuclei detected: {}".format(n_nuclei))
        print("NUCLEI_LABELS:{}".format(nuclei_path))

    if save_cells:
        n_cells = int(instances[0, 1].max().item())
        cells_path = os.path.join(args.output_dir, base + "_cell_labels.tif")
        tifffile.imwrite(cells_path, instances[0, 1].numpy().astype("uint16"))
        info("Cells detected: {}".format(n_cells))
        print("CELL_LABELS:{}".format(cells_path))

    if not save_nuclei and not save_cells:
        print("ERROR: nothing to save — check channel settings and model compatibility")
        sys.exit(1)

    info("Done.")


if __name__ == "__main__":
    main()

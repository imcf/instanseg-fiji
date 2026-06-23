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

import argparse
import os
import sys


def _read_and_extract(image_path, channel=1, z_slice=0):
    """Read an image with bioio-bioformats and extract a single channel and Z plane.

    Parameters
    ----------
    channel : int
        1-based channel index. 0 = keep all channels.
    z_slice : int
        1-based Z-slice index. 0 = max-project across all Z.

    Returns
    -------
    image_array : np.ndarray
        Shape (H, W) for single channel or (C, H, W) for all channels.
    pixel_size : float or None
        Physical pixel size in microns (X axis), or None if not in metadata.
    """
    import numpy as np
    from bioio import BioImage
    import bioio_bioformats

    img = BioImage(image_path, reader=bioio_bioformats.Reader)
    pixel_size = img.physical_pixel_sizes.X  # may be None

    # get_image_data returns a numpy array with axes CZYX
    data = img.get_image_data("CZYX")
    n_channels, n_z = data.shape[0], data.shape[1]

    # --- channel selection ---
    if channel == 0:
        selected = data  # (C, Z, Y, X)
        print("Using all {} channel(s)".format(n_channels))
    else:
        if channel > n_channels:
            raise ValueError(
                "Channel {} requested but image only has {} channel(s)".format(
                    channel, n_channels
                )
            )
        selected = data[channel - 1 : channel]  # (1, Z, Y, X)
        print("Using channel {}".format(channel))

    # --- Z selection ---
    if z_slice == 0:
        image_array = selected.max(axis=1)  # max projection -> (C, Y, X)
        print("Max-projecting {} Z-slice(s)".format(n_z))
    else:
        if z_slice > n_z:
            raise ValueError(
                "Z-slice {} requested but image only has {} Z-slice(s)".format(
                    z_slice, n_z
                )
            )
        image_array = selected[:, z_slice - 1, :, :]  # (C, Y, X)
        print("Using Z-slice {}".format(z_slice))

    return image_array.squeeze(), pixel_size


def main():
    print("Running InstanSeg inference script")
    parser = argparse.ArgumentParser(
        description="Run InstanSeg inference on a single image."
    )
    parser.add_argument("--image", required=True, help="Path to the input image")
    parser.add_argument(
        "--output-dir",
        required=True,
        dest="output_dir",
        help="Directory to write label TIFF(s) into",
    )
    parser.add_argument(
        "--model",
        default="fluorescence_nuclei_and_cells",
        help="InstanSeg model name (default: fluorescence_nuclei_and_cells)",
    )
    parser.add_argument(
        "--pixel-size",
        type=float,
        default=None,
        dest="pixel_size",
        help="Pixel size in microns. If not provided, read from image metadata.",
    )
    parser.add_argument(
        "--channel",
        type=int,
        default=1,
        help="1-based channel index to segment. 0 = use all channels (default: 1).",
    )
    parser.add_argument(
        "--z-slice",
        type=int,
        default=0,
        dest="z_slice",
        help="1-based Z-slice index to segment. 0 = max projection across all Z (default: 0).",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Device to run inference on: cpu, cuda, or mps (default: cpu).",
    )
    args = parser.parse_args()

    try:
        from instanseg import InstanSeg
    except ImportError:
        print(
            "ERROR: instanseg package not found in this Python environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import tifffile
    except ImportError:
        print(
            "ERROR: tifffile not found. Install it with: pip install tifffile",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        import bioio_bioformats  # noqa: F401 – validate before model load
    except ImportError:
        print(
            "ERROR: bioio-bioformats not found. "
            "Install it with: pip install bioio-bioformats",
            file=sys.stderr,
        )
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    print("Loading model: {} on device: {}".format(args.model, args.device))
    instanseg = InstanSeg(args.model, verbosity=1, device=args.device)

    print("Reading image: {}".format(args.image))
    image_array, pixel_size = _read_and_extract(
        args.image, channel=args.channel, z_slice=args.z_slice
    )

    # Allow explicit pixel size override (useful when metadata is missing)
    if args.pixel_size is not None:
        pixel_size = args.pixel_size
        print("Using provided pixel size: {} um/px".format(pixel_size))
    elif pixel_size is not None:
        print("Pixel size from metadata: {} um/px".format(pixel_size))
    else:
        print("WARNING: pixel size unknown, proceeding without rescaling")

    print("Running inference...")
    instances, _ = instanseg.eval_small_image(image_array, pixel_size)
    # instances shape: (1, C, H, W)  C=2 for nuclei+cells, C=1 for single output

    base = os.path.splitext(os.path.basename(args.image))[0]
    n_outputs = instances.shape[1]

    if n_outputs >= 2:
        nuclei_path = os.path.join(args.output_dir, base + "_nuclei_labels.tif")
        cells_path = os.path.join(args.output_dir, base + "_cell_labels.tif")
        tifffile.imwrite(nuclei_path, instances[0, 0].numpy().astype("uint16"))
        tifffile.imwrite(cells_path, instances[0, 1].numpy().astype("uint16"))
        print("NUCLEI_LABELS:{}".format(nuclei_path))
        print("CELL_LABELS:{}".format(cells_path))
    else:
        labels_path = os.path.join(args.output_dir, base + "_labels.tif")
        tifffile.imwrite(labels_path, instances[0, 0].numpy().astype("uint16"))
        print("LABELS:{}".format(labels_path))

    print("Done.")


if __name__ == "__main__":
    main()

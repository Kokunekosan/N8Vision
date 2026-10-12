# N8Vision

<img src="static/N8_256.png" width="128" height="128" alt="N8Vision icon">

A free, open-source visual image library with automatic image inspections,
an infinite-scroll browser, file management, and ComfyUI integration.

Current source snapshot: **I.2t-g**. This is an early release; bug reports welcome.

## Download and run

Download the complete application ZIP from this project's **Releases** page.
Extract it to a new folder on your Windows computer.

Prerequisites: Python 3.14 with the Windows `py` launcher, Git available on your
command path, internet access for installation, and enough storage for Python
dependencies and downloaded models. The installer uses an NVIDIA CUDA build
when a usable NVIDIA GPU is detected, otherwise it selects a CPU build.

1. Run `install.cmd` and let it finish downloading dependencies and weights.
2. Run `N8Vision.cmd` to start the application.
3. Choose a folder containing images and use **Scan** to make it an archive root.

Runtime data, settings, caches and model weights are created on your own machine;
they are not included in the source download. For an existing installation,
preserve those directories when replacing application source, then restart and
refresh the browser.

## Report something broken

Open this project's **Issues** tab and choose **New issue → Bug report**.
Include your version, Windows/Python details, what you did, what you expected,
what happened, and relevant logs or screenshots. Remove credentials from logs.

## What is included

- Incremental discovery of newly added images.
- Automatic Sanity and BRISQUE inspections, including unscanned archive backfill.
- Infinite-scroll image browsing and a selectable absolute inspector filepath.
- Same-root moves that preserve scroll positions and cross-root hand-truck markers.
- Sequential file moves with metadata preservation and completed-move journaling.
- ComfyUI bridge and image/refinement tools.

## Release policy

This repository holds approved source snapshots. The maintainer tests changes
in a separate live installation. Only a source snapshot that has been reviewed
and proven there is copied into this repository for publication.

The maintainer does not run the application in this publishing copy. Nothing
automatically copies machine state or unapproved changes from the live folder.

The I.2t-f audit passed dependency, syntax, scanner, startup-inspection, move and
HTTP smoke checks in the tested environment. Fresh installations, live GPU/Comfy
workflows, portal/mobile UI, and other operating systems still need broader
testing. See [RELEASE-AUDIT.txt](RELEASE-AUDIT.txt) for the scope of those checks.

## License

N8Vision source is available under the [MIT License](LICENSE). Third-party
dependencies and downloaded model weights retain their own licenses.

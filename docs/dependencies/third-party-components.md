# Third-party component inventory

Scope: `pyproject.toml`, `magical_led/`, `tests/`, the built 0.1.0 wheel and Windows x64 CPython 3.12 validation environment, 2026-11-20. Maintainer of this file: implementing developer. No bundled firmware, decompiled source, copied glyphs, Android libraries or vendor AES implementation. Python distribution metadata declares **zero mandatory runtime packages**. The `[ble]` extra installs external, unmodified wheels; they are not nested in the project wheel.

## Runtime and Windows resolution

2026-11-21 / 0.6.0 reconciliation: visual row-front rendering, verified profile
capabilities and the separate persistent-store result/commit use existing stdlib
and project modules only. No dependency, service, external effect asset, firmware
or license added. Runtime and build pins remain unchanged; every stored frame is
algorithmically authored, not copied from the Android application's assets.

2026-11-21 / 0.5.0 reconciliation: native animation encoding/transfer adds only
project code and existing stdlib use (`dataclasses`, `asyncio`, hashing for
offline previews). No third-party dependency, vendor media, firmware, new
license, remote service or distribution integration added. Existing manifest
pins and Windows dependency resolution remain unchanged. Protocol facts are
reimplemented from the user-supplied APK; no decompiled implementation is shipped.

2026-11-21 / 0.4.0 reconciliation: pre-made XMAS definitions/rendering and the
collection CLI use only existing stdlib modules. `itertools.count` supports
explicit continuous playback; there is no scheduler service or dependency.
Colors/frames are authored algorithmically, not copied from the Android app.
Manifest/build pins, runtime resolution and third-party distribution remain
unchanged. No vendor images, external assets or effect licenses introduced.

2026-11-21 / 0.3.0 reconciliation: the manifest's dependency/build pins are
unchanged. Topology parsing, transforms, JSON input and frame generation use
stdlib only (`dataclasses`, `operator`, `itertools`, `re`, `time`, `pathlib`).
NumPy is not used by the implementation or test environment; callers may pass
compatible integer arrays from their own installation. The synthetic example
and fixture contain no APK media or proprietary glyphs. No dependency added,
vendored, modified or nested into the wheel by this increment.

2026-11-21 / 0.2.0 reconciliation: `pyproject.toml` still pins Bleak 1.1.1 as
the sole optional direct runtime package and setuptools 80.9.0 as build backend.
Catalogue/scene helpers use only Python standard library additions
(`dataclasses`, `json`, `math`); no third-party additions, modifications, vendor
assets or shipped dependencies. The PowerShell launcher uses the already
inventoried interpreters and does not download tools or packages. Historical
Windows dependency versions below remain the exercised installation.

Exact results of `pip install --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp --abi cp312 --target … --report … bleak==1.1.1`. Source for each entry: `https://pypi.org/project/<name>/<version>/`; license evidence: downloaded wheel `*.dist-info/METADATA` and `LICENSE`. SHA-256 below identifies the particular wheel, not all builds of that version. A fresh pip resolution may select newer transitives.

| Package | Version | License | Purpose | Wheel SHA-256 |
|---|---|---|---|---|
| bleak | 1.1.1 | MIT | Optional scanner/client used by `magical_led.client` | `e601371396e357d95ee3c256db65b7da624c94ef6f051d47dfce93ea8361c22e` |
| winrt-runtime | 4.2.0 | MIT | Native Windows Runtime bridge for Bleak | `653f29c8b4bdfb375aa1a5830a952c9c549b583748e4dd8741f77e3ecc284a1e` |
| typing_extensions | 4.16.0 | PSF-2.0 | WinRT runtime typing support | `481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8` |
| winrt-Windows.Devices.Bluetooth | 4!10.0.28000.2957 | MIT | Adapter/device interfaces | `e39bcddf747396e2da78cb8c3d00c3e51214e5f1a9dc213fc009434c5264bbea` |
| winrt-Windows.Devices.Bluetooth.Advertisement | same | MIT | Advertising watcher | `ddf2b1bd17e92a63c892273fceb2a4aba3263123cba7be979b51e93ff7d7e32c` |
| winrt-Windows.Devices.Bluetooth.GenericAttributeProfile | same | MIT | GATT operations | `3e95b316a941106fd8193dead1a31e6abf9f118efceb58da2388e943fcf5f6d8` |
| winrt-Windows.Devices.Enumeration | same | MIT | Device discovery | `0d76f1961bede3dfaf92939ca16edb882daa97bf6481e2dadc8174fec64e7a7e` |
| winrt-Windows.Foundation | same | MIT | WinRT async operations | `0669de7ce480806a0f9a46d005837799e37f1738911b54c4bc04788b37974e69` |
| winrt-Windows.Foundation.Collections | same | MIT | WinRT collections | `0401c1b6ed512d1fdad8ba1571698e9000ebee6a69781db9a01994ffcc54a503` |
| winrt-Windows.Storage.Streams | same | MIT | GATT data buffers | `e113832320f2e7f8b09cedfb400cb7eaf0ac769ad1f2038ddbe88801497916c4` |

On Linux Bleak declares `dbus-fast>=1.83.0`; on macOS `pyobjc-core`, `pyobjc-framework-CoreBluetooth` and `pyobjc-framework-libdispatch` (each >=10.3). No non-Windows installation resolved or shipped in this increment. Obtain target-specific wheel versions, licenses and transitive resolution before distributing a packaged environment there.

## Development and analysis tools (not part of project wheel)

| Component / source | Use and evidence |
|---|---|
| CPython 3.12.12, Inkscape-bundled GCC/UCRT build | Standard library incl. `unittest`, `asyncio`, `argparse`, `zipfile`, `struct`; local analysis, build and tests. PSF License plus upstream notices. No Python runtime bundled. |
| CPython 3.12.10 embedded x64, python.org | Windows standard ABI backend validation; upstream ZIP includes `LICENSE.txt`. |
| setuptools 80.9.0, PyPI (MIT) | PEP 517 build backend, `pyproject.toml`; isolated wheel, its `.dist-info/licenses` and vendored manifests are upstream evidence. |
| pip 25.3, PyPI (MIT) | Validation-only builder frontend/resolver/installer; `.dist-info/licenses` and `_vendor/vendor.txt`. |
| PowerShell 7.6.10 (Microsoft, MIT) / .NET cryptography | Local ZIP/hash/inspection, independent AES calculation; system tooling, not shipped. |
| GNU binutils 2.47 (GNU, GPL), Arch Linux WSL | `objdump` / `readelf` static disassembly/relocations of native x86-64 ELF, no linking. |
| Git for Windows 2.56.0.windows.2 (GPL-2.0) | Local milestones only. |
| Magical LED Android base APK + mdpi split (user input, rights not assumed) | Static analysis only, see [input hashes](../protocol.md). No APK components in project artifacts. |

For tooling reproducibility, pip 25.3's vendored set includes CacheControl 0.14.3, distlib 0.4.0, distro 1.9.0, msgpack 1.1.2, packaging 25.0, platformdirs 4.5.0, pyproject-hooks 1.2.0, requests 2.32.5, certifi 2025.10.5, idna 3.10, urllib3 1.26.20, rich 14.2.0, pygments 2.19.2, resolvelib 1.2.1, setuptools 70.3.0, tomli 2.3.0, tomli-w 1.2.0, truststore 0.10.4 and dependency-groups 1.3.1. The build backend's `_vendor` metadata identifies autocommand 2.2.2, backports.tarfile 1.2.0, importlib_metadata 8.0.0, inflect 7.3.1, jaraco.collections 5.1.0, jaraco.context 5.3.0, jaraco.functools 4.0.1, jaraco.text 3.12.1, more-itertools 10.3.0, packaging 24.2, platformdirs 4.2.2, tomli 2.0.1, typeguard 4.3.0, typing_extensions 4.12.2, wheel 0.45.1 and zipp 3.19.2. These are parts of third-party **tools**, not application dependencies; consult those exact wheels' license files for the individual notices.

**Project license (2026-11-22):** the owner selected MIT and the copyright notice
“Copyright (c) 2026 py-magical-led contributors”. The authoritative text is
[`LICENSE`](../../LICENSE); package metadata declares SPDX expression `MIT`
and includes the license file in distributions. This licenses the project's
own code/documentation, not the analyzed APK or separately licensed dependencies.

**Distribution status:** local development only. No upstream dependency modified or redistributed in this wheel. Preserve upstream copyright/license notices if bundling any dependency; do not infer a license for the APK or its assets. Human third-party distribution/license review remains pending before publication. No rights determination is implied by a passing test.

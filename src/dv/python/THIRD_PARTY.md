# Python verification dependencies

The Python testbench path uses CPython **3.12.14** (PSF-2.0),
[cocotb 2.0.1](https://github.com/cocotb/cocotb/tree/v2.0.1) (BSD-3-Clause),
and [find-libpython 0.4.1](https://pypi.org/project/find-libpython/0.4.1/)
(MIT). [requirements.txt](requirements.txt) pins the installed packages.
These are unmodified external tools. Upstream notices remain in their installed
distributions. No dependency source is copied into the repository.

This separate environment does not change the regular builder Python pin.
The builder records the executing interpreter, embedded Python library and
cocotb native library paths and hashes, package versions and installed file
hashes. Interpreter and embedded-library patch versions may differ in a bundled
runtime; retain the simulator's embedded version banner and both identities.
Questa remains the installed proprietary RTL simulator under the existing
[tool notice](../../../tools/sim/THIRD_PARTY.md).

Original tests and the deliberate fault wrapper were written for this repository
from the approved joypad contract. Existing SV testbench code is not imported.

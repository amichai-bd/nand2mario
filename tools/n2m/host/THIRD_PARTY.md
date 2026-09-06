# Serial backend provenance

The optional physical backend uses unmodified pySerial 3.5, by Chris Liechti and
contributors, under its BSD license. No third-party source is copied here.

- [Release metadata](https://pypi.org/pypi/pyserial/3.5/json)
- [Source and license at v3.5](https://github.com/pyserial/pyserial/tree/v3.5)
- [API documentation](https://pyserial.readthedocs.io/en/latest/pyserial_api.html)
- Distribution: `pyserial-3.5-py2.py3-none-any.whl`
- SHA-256: `c4451db6ba391ca6ca299fb3ec7bae67a5c55dde170964c7a14ceefec02f2cf0`

Install explicitly with `python -m pip install --require-hashes --only-binary=:all:
-r tools/n2m/host/requirements.txt`. Commands never install or download it.
Host tests use an independent fake endpoint and the Python standard library.
The API version is checked before creating a physical serial connection.

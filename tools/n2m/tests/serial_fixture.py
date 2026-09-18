"""A fake Linux serial inventory: udev by-id links over real sysfs-shaped attributes.

The healthy entries point at character devices every user may read and write,
so the health rule runs for real instead of being stubbed. Nothing here opens a
device: the links and attribute files are only read.
"""
from pathlib import Path

# Real character devices, so node_state classifies actual nodes.
HEALTHY_NODES = ("/dev/null", "/dev/zero")
MISSING_NODE = "dev/ttyUSB9"


def usb_device(base, name, *, vid, pid, serial, manufacturer="Example Systems", product="Serial Bridge"):
    """Write one USB device's sysfs attributes and return its directory."""
    device = Path(base) / "sys/devices/usb1" / name
    device.mkdir(parents=True, exist_ok=True)
    for attribute, value in (("idVendor", vid), ("idProduct", pid), ("serial", serial),
                             ("manufacturer", manufacturer), ("product", product)):
        (device / attribute).write_text(value + "\n", encoding="utf-8")
    return device


def port(base, link_name, node, device):
    """Name `node` in the by-id directory and bind its tty to `device` in sysfs.

    With `device` None the tty carries no USB device, which is the case
    enumeration skips because it has no stable identity to select by.
    """
    base = Path(base)
    by_id = base / "dev/serial/by-id"
    by_id.mkdir(parents=True, exist_ok=True)
    (by_id / link_name).symlink_to(node)
    tty = base / "sys/class/tty" / Path(node).name
    tty.mkdir(parents=True, exist_ok=True)
    interface = (device if device is not None else base / "sys/devices/platform") / "interface:1.0"
    interface.mkdir(parents=True, exist_ok=True)
    (tty / "device").symlink_to(interface)


def inventory(base):
    """Build the shared fixture and return (by-id directory, tty class directory).

    Four udev names: one healthy FTDI-style bridge, one healthy bridge with
    another vendor and product, one whose device node is gone, and one with no
    USB device behind it.
    """
    base = Path(base)
    first = usb_device(base, "1-1", vid="0403", pid="6001", serial="ABC123")
    second = usb_device(base, "1-2", vid="1234", pid="5678", serial="DEF456",
                        manufacturer="Other Vendor", product="Debug Cable")
    gone = usb_device(base, "1-3", vid="0403", pid="6001", serial="GONE01")
    port(base, "usb-Example_Systems_Serial_Bridge_ABC123-if00-port0", HEALTHY_NODES[0], first)
    port(base, "usb-Other_Vendor_Debug_Cable_DEF456-if00-port0", HEALTHY_NODES[1], second)
    port(base, "usb-Example_Systems_Serial_Bridge_GONE01-if00-port0", str(base / MISSING_NODE), gone)
    port(base, "usb-Platform_Serial_0-if00-port0", "/dev/full", None)
    return base / "dev/serial/by-id", base / "sys/class/tty"


# The identities the fixture's enumeration produces, in by-id name order.
HEALTHY_IDENTITY = "USB\\VID_0403&PID_6001\\Example_Systems_Serial_Bridge_ABC123-if00-port0"
OTHER_IDENTITY = "USB\\VID_1234&PID_5678\\Other_Vendor_Debug_Cable_DEF456-if00-port0"
UNHEALTHY_IDENTITY = "USB\\VID_0403&PID_6001\\Example_Systems_Serial_Bridge_GONE01-if00-port0"

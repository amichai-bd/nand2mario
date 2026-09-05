"""Generate checked endpoint collections from declarative timing assignments."""
import re


def validate(value):
    if not isinstance(value, dict) or set(value) != {"async_reset_pins", "output_delays"}:
        raise ValueError("invalid checked timing assignments")
    pins = value["async_reset_pins"]
    if not isinstance(pins, list) or not pins or len(set(pins)) != len(pins):
        raise ValueError("invalid asynchronous reset endpoints")
    for pin in pins:
        if not isinstance(pin, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_|]*(?:\[\d+\])?\|clrn", pin):
            raise ValueError("asynchronous exception requires an exact reset pin")
    if not isinstance(value["output_delays"], list) or not value["output_delays"]:
        raise ValueError("missing checked output delays")
    for entry in value["output_delays"]:
        if not isinstance(entry, dict) or set(entry) != {"clock", "ports", "count"}:
            raise ValueError("invalid checked output delay")
        if not isinstance(entry["clock"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_|]*(?:\[\d+\])?", entry["clock"]):
            raise ValueError("output delay requires an exact clock")
        if type(entry["count"]) is not int or entry["count"] < 1:
            raise ValueError("invalid checked output count")
        if not isinstance(entry["ports"], list) or not entry["ports"] or any(not isinstance(p, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[(?:\d+|\*)\])?", p) for p in entry["ports"]):
            raise ValueError("invalid checked output ports")


def generate(value, quote):
    validate(value)
    lines = []
    def collection(kind, names, count, variable):
        words = " ".join(quote(name) for name in names)
        lines.append(f'set {variable} [get_{kind} [list {words}]]')
        lines.append(f'if {{[get_collection_size ${variable}] != {count}}} {{error "checked endpoint count mismatch: {variable}"}}')
    for i, pin in enumerate(value["async_reset_pins"]):
        collection("pins", [pin], 1, f"reset_{i}")
        lines.append(f"set_false_path -to $reset_{i}")
    for i, entry in enumerate(value["output_delays"]):
        collection("clocks", [entry["clock"]], 1, f"clock_{i}")
        collection("ports", entry["ports"], entry["count"], f"ports_{i}")
        lines.extend([f"set_output_delay -clock $clock_{i} -source_latency_included -max 2.000 $ports_{i}",
                      f"set_output_delay -clock $clock_{i} -source_latency_included -min 0.000 $ports_{i}"])
    return "\n".join(lines) + "\n"

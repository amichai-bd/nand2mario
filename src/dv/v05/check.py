"""Independent streaming check of the complete original v0.5 trace."""
import csv
from pathlib import Path

from reference import (FIRST_IMAGE_END, FRAME_DOTS, INPUT_MASKS, WINDOW_END,
                       Reference, compare_record, input_window, pixel_shade,
                       unpack_retirement)


def validate_inputs(events):
    if len(events) != len(INPUT_MASKS):
        raise ValueError("V05_INPUT_COUNT")
    result = []
    for index, (event, mask) in enumerate(zip(events, INPUT_MASKS), 1):
        if set(event) != {"dot", "buttons"} or type(event["dot"]) is not int:
            raise ValueError("V05_INPUT_FIELDS")
        low, high = input_window(index)
        if type(event["buttons"]) is not int or event["buttons"] != mask or not low <= event["dot"] <= high:
            raise ValueError(f"V05_INPUT_WINDOW transition={index} expected={mask} actual={event}")
        result.append((event["dot"], mask))
    return result


def check(folder: Path, events, pause_dot):
    journal = validate_inputs(events)
    if type(pause_dot) is not int or not WINDOW_END <= pause_dot <= WINDOW_END + 2000:
        raise ValueError("V05_PAUSE_WINDOW")
    # Includes any last VBlank wake/update before the actual host pause.
    reference = Reference(journal)
    count = 0
    with (folder / "retirement.csv").open(newline="") as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != ["seq", "record"]:
            raise ValueError("V05_RETIRE_HEADER")
        for expected in reference.records(pause_dot):
            row = next(rows, None)
            if row is None or int(row["seq"]) != count:
                raise ValueError(f"V05_RETIRE_MISSING seq={count}")
            compare_record(expected, unpack_retirement(row["record"]))
            count += 1
        if next(rows, None) is not None:
            raise ValueError("V05_RETIRE_EXTRA")
    pixel_count = 0
    with (folder / "pixels.csv").open(newline="") as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != ["frame", "index", "dot", "shade"]:
            raise ValueError("V05_PIXEL_HEADER")
        for frame in range(602):
            for index in range(23040):
                row = next(rows, None)
                if row is None or int(row["frame"]) != frame or int(row["index"]) != index:
                    raise ValueError(f"V05_PIXEL_MISSING frame={frame} index={index}")
                x, y = index % 160, index // 160
                shade = pixel_shade(frame, x, y)
                if int(row["shade"]) != shade:
                    raise ValueError(f"V05_PIXEL frame={frame} index={index} expected={shade} actual={row['shade']}")
                if frame:
                    dot = FIRST_IMAGE_END - 143 * 456 - 159 + (frame - 1) * FRAME_DOTS + y * 456 + x
                    if int(row["dot"]) != dot:
                        raise ValueError(f"V05_PIXEL_DOT frame={frame} index={index} expected={dot} actual={row['dot']}")
                pixel_count += 1
        if next(rows, None) is not None:
            raise ValueError("V05_PIXEL_EXTRA")
    return {"retirements": count, "pixels": pixel_count, "inputs": len(journal),
            "first_image_dot": FIRST_IMAGE_END, "window_end": WINDOW_END,
            "pause_dot": pause_dot}

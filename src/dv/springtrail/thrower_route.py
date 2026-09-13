"""Frozen ordinary input history for the original coin promotion."""

# Start, cross the first gap/patrol, acquire the mushroom, cross CURL and
# the second gap, acquire the coin, release B, then fire. No state operands.
SCRIPT = ((161,1),(33,96),(49,12),(33,40),(49,12),(33,29),
          (16,12),(0,40),(49,12),(33,13),(49,1),(33,108),
          (16,12),(0,20),(32,1))
LIMITS = {'thrower-short': 242, 'thrower': 409}
CHECKPOINTS = {0:'title',242:'large',388:'promoted',409:'shot'}
CAPS = {'thrower-short':120,'thrower':180}


def masks():
    return [mask for mask,count in SCRIPT for _ in range(count)]

"""Run the unchanged integration scenario after validated preload adoption."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'integration'))
from peer import main

if __name__ == '__main__':
    main(preloaded=True)

"""The fixture peer with a deliberate protocol fault: an undeclared WAIT after the first request."""
from peer_check import main

if __name__ == "__main__":
    main(fault=True)

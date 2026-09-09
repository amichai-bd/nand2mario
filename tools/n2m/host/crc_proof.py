"""Fixed malformed PING proof; ordinary Client timeout semantics stay unchanged."""
from .. import generated_interfaces as abi
from ..interface_codec import cobs_decode, cobs_encode, encode_packet
from .client import Client, summary


def state(client):
    values = {name: client.read_host(getattr(abi, 'HOST_REG_' + name))
              for name in ('STATE', 'INPUT_SOURCE', 'INPUT', 'INPUT_EFFECTIVE')}
    if values != {'STATE': abi.STATE_PAUSED, 'INPUT_SOURCE': 0,
                  'INPUT': 0, 'INPUT_EFFECTIVE': 0}:
        raise ValueError('CRC proof requires PAUSED, UART source and zero input')
    # Split counters are stable only after the paused-state prerequisite.
    for name in ('DOT_LO', 'DOT_HI', 'RETIRE_LO', 'RETIRE_HI'):
        values[name] = client.read_host(getattr(abi, 'HOST_REG_' + name))
    return values


def run(client):
    before = state(client)
    sequence = client.sequence
    following = (sequence + 1) & client.sequence_mask
    raw = bytearray(cobs_decode(encode_packet(sequence, abi.COMMAND_PING)[:-1]))
    raw[-2] ^= 1
    packet = cobs_encode(raw) + b'\0'
    client.persist(following, True)
    client.uncertain = True
    client.record({'event': 'malformed_ping', 'sequence': sequence,
                   'packet': summary(packet), 'crc_xor': 1})
    started = client.clock()
    if client.transport.write(packet) != len(packet):
        raise OSError('short malformed PING write')
    # Start the observation after the complete write, not before transmission.
    received = client.transport.observe(abi.WIRE_RESPONSE_TIMEOUT_MS / 1000)
    if received:
        client.record({'event': 'unexpected_bytes', 'received': summary(received)})
        raise ValueError('malformed PING produced bytes')
    client.record({'event': 'crc_silence', 'seconds': client.clock() - started})
    # The complete diagnostic remains pending even after each valid read reply.
    recovery = Client(client.transport, sequence=following, record=client.record,
                      persist=lambda token, pending: client.persist(token, True),
                      clock=client.clock)
    if recovery.request('PING')['value'] != abi.WIRE_ABI:
        raise ValueError('recovery PING ABI mismatch')
    after = state(recovery)
    if after != before:
        raise ValueError('CRC proof changed public state or counters')
    client.persist(recovery.sequence, False)
    client.record({'event': 'crc_proof_complete', 'before': before, 'after': after})
    return {'before': before, 'after': after, 'malformed_sequence': sequence,
            'recovery_sequence': following, 'silence_seconds': abi.WIRE_RESPONSE_TIMEOUT_MS / 1000}

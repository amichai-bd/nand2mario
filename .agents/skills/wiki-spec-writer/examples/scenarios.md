# Scenarios

Good: Define a UART packet's byte order, length bounds, checksum coverage,
timeout, reset state, and error response.

Bad: Say the protocol is "simple and robust" or paste implementation history
into the contract.

Good: State that a physical UART test is still missing, name its required
observations and link the open verification issue.

Bad: Keep a closed implementation issue as the UART module's owner or cite its
merge PR instead of linking the module and tests.

Exception: The repository statistics page may report dated issue/PR delivery
history. External issue/PR citations may supply technical source material.

Not a trigger: Post build evidence to a PR without changing behavior.

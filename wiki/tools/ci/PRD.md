# Trusted product CI requirements

Provide explicitly invoked validation of a reviewed main revision using fixed
Questa and Quartus profiles, without registering a self-hosted runner or accepting
remote commands. The [design](SPEC.md) owns admission, evidence, locking and
status interpretation; [the builder](../n2m/SPEC.md) owns tool execution records.

The [controller](../../../tools/ci/controller.py) must be
reviewable and testable with host fixtures while remaining inactive. Admission
must bind repository, workflow identity/content, source SHA, account, active run,
attempt and profile. Cancellation, replay, changed trust state and incomplete
records cannot produce success. Recovery preserves failed or interrupted attempts
and requires a new remote attempt.

The hosted result is authenticated controller attestation. It does not independently
prove unseen local logs or artifacts. Independent review must audit retained
command, input, tool and artifact evidence bound by the canonical envelope digest.

Actual configured licensed execution and activation remain
[an open CI gap](https://github.com/amichai-bd/nand2mario/issues/32). The inactive
implementation does not change repository protection, environments, credentials or
runner registration. Physical execution is absent; setup and acceptance remain
[an open board gap](https://github.com/amichai-bd/nand2mario/issues/28). Explicit invocation is
not unattended CI and does not establish proof for a different revision.

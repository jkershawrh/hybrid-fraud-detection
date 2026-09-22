# Launchpad intake candidate image

The `Lint and Test` workflow has an opt-in, manual-only candidate publisher. A normal push or workflow dispatch does not publish an image. The publisher runs only on `codex/hybrid-fraud-immutable-images`, only when `publish_candidate` is true, and only when `expected_revision` exactly matches the dispatched commit. All eight ordinary CI jobs must pass first.

Before enabling it, configure the GitHub environment `intake-candidate-publish` with an appropriate reviewer gate and these environment secrets:

- `QUAY_ROBOT_USERNAME`: a `redhat-gpte+...` robot identity with write access only to `quay.io/redhat-gpte/hybrid-fraud-detection`.
- `QUAY_ROBOT_TOKEN`: that robot's token. Never place it in the repository, command line, or Launchpad intake.

Dispatch the existing `Lint and Test` workflow on the source branch with `publish_candidate=true` and `expected_revision=<full 40-character commit SHA>`. The job builds `linux/amd64`, checks readiness and a sample score, pushes a unique `intake-<sha>-<run>-<attempt>` tag, and records the registry digest. It generates an SPDX JSON SBOM, signs the digest and attests the SBOM and source identity using GitHub OIDC, then verifies the expected workflow identity. The job summary reports the immutable `quay.io/redhat-gpte/hybrid-fraud-detection@sha256:...` reference. A failed signing or verification step leaves an unusable candidate tag, not an approved release.

Do not commit the resulting image digest back into this source repository solely to match its own source revision: that creates a commit/digest cycle. Launchpad should pin this repository's source commit and supply the approved image digest as a separately reviewed `runtime.workload.helm_values.app.image` override. Its trusted render must bind the exact source commit, override, and output digest. The chart's default `:latest` remains blocked by intake until that override and its signature, SBOM, provenance, architecture, cold-pull, runtime, and cleanup evidence are accepted. No workflow step activates a Launchpad catalog item or deploys to a cluster.

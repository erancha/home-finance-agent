# 0007. A guest on the loan-simulator EC2 instance, behind its own CloudFront

- Status: Accepted
- Date: 2026-11-16

## Context

The stack ran only on a workstation ([ADR 0005](0005-docker-compose-stack.md)), and Google
sign-in accepts only `localhost` or a public hostname, so nobody else could reach it. The
loan-simulator repo already runs an ARM instance (t4g.small) behind CloudFront, built so other
Docker Compose repos can deploy onto it as guests, and the card agents amex-agent and cal-agent
deploy there too. The heavy work is the model's API call; the agent and its database are small,
and there are no real users yet.

## Decision

`deploy.sh --ec2` runs the same Compose stack on that instance as a guest of the loan-simulator
stack, with a CloudFront distribution of its own in front as the only way in.

- This repo's CloudFormation stack, from the same template every Docker Compose repo shares,
  opens the edge's port 8010 to CloudFront's servers in the instance's security group and points
  its distribution at the instance's fixed address. TLS ends at CloudFront.
- The images are built on the deployer's machine for ARM and loaded into the instance's Docker
  daemon over SSH; Compose runs there against the daemon. Nothing is bind-mounted from the
  deployer's machine: the edge's configuration is baked into its image, and the card-agent
  registry reaches the manager as a Compose secret copied into the container.
- The card agents are reached at `host.docker.internal` on the instance, as on a workstation;
  a separate registry holds the CloudFront addresses a person's browser opens their pages at.

## Consequences

- No instance, address or disk of its own to pay for or operate; the loan-simulator stack must
  be deployed first, and it cannot be deleted while this stack runs on its instance.
- Four stacks share 2 GB of memory; this one's limits alone add up to about 1.4 GB.
- The instance is a single point of failure, and its disk has no snapshots; the data moves with
  `tools/sql-helper.sh --backup` and `--restore`.
- CloudFront cuts a response that is silent for 30 seconds; the event stream sends a comment
  every 15 seconds.

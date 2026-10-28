# rail-aws-rag

A small RAG assistant over EU railway law, provisioned on AWS with Terraform, kept under a CI quality gate, and designed to cost a few dollars a month or nothing when destroyed.

**Status: work in progress.** Nothing is deployed yet. This README gets its architecture diagram, measured costs and results as each milestone is built and measured.

## Milestones

1. Budgets alert at 1 USD and 5 USD, defined in Terraform (first resource, before anything else).
2. Remote Terraform state in S3 with native locking.
3. Offline embeddings and an S3 vector store.
4. Lambda handler with Bedrock and Guardrails.
5. API Gateway, throttling and monitoring.
6. GitHub Actions with OIDC.
7. goldpass quality gate against the deployed endpoint.

## Licence

MIT. See [LICENSE](LICENSE). The rail corpus comes from EUR-Lex; see the source and licence notes in the original [rail-regulation-rag](https://github.com/cardohso/rail-regulation-rag) repository.

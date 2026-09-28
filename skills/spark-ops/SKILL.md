---
name: spark-ops
description: Inspect a DGX Spark node and prepare user-level model and document-tool services. Use when deploying this repository or diagnosing local inference failures on the node assigned to the team.
---

# Spark Operations

Read the team's node access manual before deployment. Use only the allocated node. Keep credentials and allocated network details out of published material.

## Workflow

1. Read the node architecture, available disk space and GPU identity using read-only system commands. Keep at least 20 percent disk space available.
2. Inspect existing user-level environments and services before installing anything. Reuse working dependencies when appropriate.
3. Use a virtual environment, user directory or permitted container. Run persistent tasks in tmux. Keep model endpoints local and protect any externally accessible application with authentication.
4. Set the actual installed model tag explicitly. Monitor measured use and errors; do not invent a memory budget, throughput multiplier or concurrent stream count.
5. On resource failure, report the error and propose a smaller workload. Do not kill unrelated jobs or change system configuration.

## Not implemented

Automatic memory scheduling, llama-swap integration and a budget-check script are future work. This Skill does not claim they run at application startup.

## Guardrails

Do not reboot or shut down the node, alter accounts, firewall, drivers or networking, or access another team's node. Do not upload files larger than 1 GB using SCP. Back up project outputs before the organizer reclaims the machine.

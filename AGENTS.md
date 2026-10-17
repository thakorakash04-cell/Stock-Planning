# Maintaining the planning assistant
When changing calculations, production windows, source definitions, permissions or user-visible workflows:
- Update PLANNING_RULES.md and the relevant README section to match the final implemented behavior.
- Preserve the distinction between the original PS ordering rule, physical BOM availability and forecast purchasing dates.
- Use shared server calculation functions for assistant tools; do not duplicate business arithmetic in model prompts.
- Register a new read-only operation in stock_accounts/planning_assistant.py when a new feature needs multi-table calculations. Source discovery does not automatically grant executable tools.
- Keep the deployed knowledge source allowlist current; never include credentials, authentication stores, personal chat logs or secret files.
- Increment relevant hot-deployment revision constants when changing cached helper behavior, and update regression checks.
- Verify rule accuracy, permissions, read-only behavior, follow-up scenario handling and evidence downloads for affected operations.
- Do not claim model training, permanent conversation memory or knowledge of GitHub changes before deployment.

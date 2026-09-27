import { t } from "./i18n";
const templates = [
  {
    id: "cicd",
    code: "05",
    area: "DevOps",
    title: "Review a CI/CD pipeline",
    description:
      "Assess build reproducibility, release gates, deployment safety and rollback evidence.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nPipeline definition and pinned actions; failed job logs; artifact promotion; environment approvals; rollback procedure.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "kubernetes",
    code: "06",
    area: "Platform Engineering",
    title: "Review a Kubernetes workload",
    description:
      "Check workload health, requests and limits, probes, disruption budgets and rollout behavior.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nRedacted manifests; pod events; requests and limits; readiness/liveness probes; PDB; HPA signals; recent rollout.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "iac",
    code: "07",
    area: "DevOps",
    title: "Review Infrastructure as Code",
    description:
      "Inspect a proposed infrastructure change, drift, state protection and recovery prerequisites.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nRedacted Terraform/Bicep/CloudFormation diff and plan; state backend; drift findings; policy checks; recovery path.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "supply-chain",
    code: "08",
    area: "DevSecOps",
    title: "Review software supply chain risks",
    description:
      "Connect dependency findings to shipped artifacts, provenance and available fixes.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nSBOM and exact artifact digests; scanner database date; advisory links; exploit prerequisites; signed builds; deployment exposure.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "secrets",
    code: "09",
    area: "DevSecOps",
    title: "Review secrets and workload identity",
    description:
      "Assess secret distribution, rotation, OIDC trust and CI permissions without revealing credentials.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nRedacted identity policies and OIDC claims; token lifetime; secret references only; rotation evidence; least-privilege requirements.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "cloud-design",
    code: "10",
    area: "Cloud Architecture",
    title: "Review a cloud architecture",
    description:
      "Evaluate trust boundaries, networking, resilience and operational trade-offs against requirements.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nArchitecture diagram; traffic and data sensitivity; regions and zones; private endpoints; identity boundaries; constraints and ADRs.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "disaster-recovery",
    code: "11",
    area: "SRE",
    title: "Prepare a disaster recovery exercise",
    description:
      "Compare recovery objectives with actual backup, restore and failover evidence.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nRTO/RPO targets; backup scope; last verified restore; dependencies; failover runbook; exercise isolation and success criteria.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "slo",
    code: "12",
    area: "SRE",
    title: "Review SLOs and alert quality",
    description:
      "Evaluate user-facing indicators, error budgets and actionable alert conditions.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nUser journeys; SLI definitions and queries; SLO window; error-budget burn; alert history; ownership and runbook links.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "threat-model",
    code: "13",
    area: "Security Engineering",
    title: "Build a threat model",
    description:
      "Identify assets, entry points and abuse paths, then relate controls to evidence.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nSystem/data-flow diagram; assets; trust boundaries; attacker capabilities; authentication flows; existing controls; testable assumptions.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "security-response",
    code: "14",
    area: "Security Engineering",
    title: "Triage a security finding",
    description:
      "Distinguish confirmed evidence from hypotheses and prepare a contained investigation.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nFinding provenance and timestamps; affected versions; redacted indicators; exposure; existing mitigations; authorised scope and evidence handling.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "developer-platform",
    code: "15",
    area: "Platform Engineering",
    title: "Design a developer platform capability",
    description:
      "Define a useful paved road with clear interfaces, ownership, adoption measures and escape hatches.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nDeveloper journey; current friction; service contract; self-service boundaries; templates; onboarding measures; ownership and support model.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "observability",
    code: "16",
    area: "Platform Engineering",
    title: "Review an observability pipeline",
    description:
      "Trace telemetry from collection to storage, dashboards and incident response.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nCollector configuration; trace/log/metric samples without secrets; cardinality; retention; sampling; dropped signals; alert-to-runbook linkage.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "finops",
    code: "17",
    area: "Cloud Architecture",
    title: "Review capacity and cloud cost",
    description:
      "Compare measured utilisation, service requirements and cost drivers before recommending changes.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nBilling period and currency; tagged allocation; utilisation percentiles; workload forecasts; availability constraints; pricing assumptions.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
  {
    id: "agent-evaluation",
    code: "18",
    area: "AI Agentic Engineering",
    title: "Evaluate an agentic workflow",
    description:
      "Review tool authority, grounding, failure recovery, evaluation coverage and token budgets.",
    draft:
      "Scope and environment:\n\nObserved facts and timestamps:\n\nEvidence to provide:\nWorkflow graph; MCP tool schemas and permissions; representative success/failure cases; injection cases; measured token usage; latency; human gates.\n\nQuestion and expected deliverable:\n\nConstraints: read-only assessment; no deployment, scanning or remediation without a separate explicit operator action.\n\nCite exact relevant runbook passages. If the knowledge is missing, say so and list the missing evidence. Never invent an assessment result.\n",
  },
] as const;
export const specialistMissions = templates.map((item) => ({
  id: item.id,
  code: item.code,
  area: item.area,
  category: item.area,
  get title() {
    return t(item.title);
  },
  get description() {
    return t(item.description);
  },
  get draftTitle() {
    return t(item.title);
  },
  get draft() {
    return t(item.draft);
  },
}));

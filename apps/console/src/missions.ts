import { t } from "./i18n";
import { specialistMissions } from "./mission-templates";
const sreMissions = [
  {
    id: "incident",
    code: "01",
    get title() {
      return t("Investigate an incident");
    },
    category: "TRIAGE",
    get description() {
      return t(
        "Turn a production signal into a sourced diagnosis and a proposal to review.",
      );
    },
    get draftTitle() {
      return t("Incident investigation");
    },
    get draft() {
      return t(
        "Observed symptoms:\n\nAffected service and environment:\n\nFirst observed (with timezone):\n\nRelevant metrics and redacted errors:\n\nRecent changes:\n\nChecks already performed:\n\nImpact and constraints:\n",
      );
    },
  },
  {
    id: "latency",
    code: "02",
    get title() {
      return t("Trace a slowdown");
    },
    category: "PERFORMANCE",
    get description() {
      return t(
        "Bring latency measurements, saturation signals and a timeline to the investigation.",
      );
    },
    get draftTitle() {
      return t("Latency investigation");
    },
    get draft() {
      return t(
        "Affected service and environment:\n\nNormal latency and observed latency (p50/p95/p99):\n\nTime window (with timezone):\n\nTraffic, error rate and resource saturation:\n\nRecent deployments or configuration changes:\n\nRedacted logs and checks already performed:\n",
      );
    },
  },
  {
    id: "capacity",
    code: "03",
    get title() {
      return t("Understand saturation");
    },
    get category() {
      return t("CAPACITY");
    },
    get description() {
      return t(
        "Investigate exhausted connections, memory pressure or resource limits with evidence.",
      );
    },
    get draftTitle() {
      return t("Resource saturation investigation");
    },
    get draft() {
      return t(
        "Affected resource and service:\n\nConfigured capacity and observed usage:\n\nTime window and growth pattern:\n\nUser impact and related errors:\n\nRelevant runbooks and previous checks:\n\nOperational constraints:\n",
      );
    },
  },
  {
    id: "change",
    code: "04",
    get title() {
      return t("Investigate a regression");
    },
    get category() {
      return t("CHANGE REVIEW");
    },
    get description() {
      return t(
        "Connect a new symptom to recent changes and review the documented recovery options.",
      );
    },
    get draftTitle() {
      return t("Post-change regression investigation");
    },
    get draft() {
      return t(
        "Affected service and environment:\n\nChange description and deployment time:\n\nSymptoms before and after the change:\n\nRelevant metrics and redacted errors:\n\nDocumented rollback procedure, if available:\n\nConstraints and checks already performed:\n",
      );
    },
  },
] as const;
export const missions = [
  ...sreMissions.map((mission) => Object.assign(mission, { area: "SRE" })),
  ...specialistMissions,
];
export const findMission = (id: string | null) =>
  missions.find((mission) => mission.id === id);

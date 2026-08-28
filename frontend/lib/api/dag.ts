/**
 * Typed client for the causal graph behind a diagnosis.
 *
 * Snake_case on the wire, like the rest of the cases router. Structure and
 * traversal arrive together because they are always rendered together — a
 * diagram with no highlighted path explains nothing, and a path with no diagram
 * is a list of node ids.
 */

import { request } from "@/lib/api/client";

export type CausalNodeType = "observable" | "root_cause";

export interface CausalDagNode {
  node_id: string;
  node_type: CausalNodeType;
  label: string;
  description: string;
  /** Root causes only: how likely this was before any evidence. */
  prior_probability: number | null;
  /** Observables only: how often it fires when something else is driving. */
  base_rate: number | null;
}

export interface CausalDagEdge {
  from: string;
  to: string;
  /** `P(symptom | cause)`. */
  likelihood: number;
}

export interface CausalTraversal {
  observed_features: Record<string, boolean>;
  posteriors: Record<string, number>;
  causal_path: string[];
  root_cause: string;
  posterior_probability: number;
  alternative_hypotheses: Array<{ cause: string; probability: number }>;
}

export interface CaseDag {
  playbook: string;
  dag_version: string;
  nodes: CausalDagNode[];
  edges: CausalDagEdge[];
  /**
   * Null for a case diagnosed before Phase 12, or by the model-led fallback.
   * The section is hidden in that state rather than drawing an unlit graph.
   */
  traversal: CausalTraversal | null;
}

export function fetchCaseDag(caseId: string): Promise<CaseDag> {
  return request<CaseDag>(`/api/cases/${caseId}/dag`);
}

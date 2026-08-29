"use client";

/**
 * The reasoning behind a diagnosis, as a graph you can look at.
 *
 * Symptoms on the left, causes on the right, and the route between them lit up.
 * The claim this section makes is that the confidence number on the case detail
 * came from somewhere specific — so the point of the picture is not that it is
 * pretty, it is that every node in the highlighted path is a fact the agent
 * checked, and every node beside it is one it checked and ruled out.
 *
 * **Layout is computed, not authored.** Dagre places the nodes left-to-right
 * from the edge list. Hand-positioning fifteen nodes would look better once and
 * then be wrong the first time a node was added to `definitions.py` — and the
 * graph is meant to be edited, since it is where the domain knowledge lives.
 *
 * **Colour never carries meaning alone.** A node on the causal path has a brand
 * ring *and* a filled dot *and* the word "observed"; the diagnosed cause is
 * filled *and* labelled with its probability; a ruled-out cause is dimmed *and*
 * shows its posterior in the panel beside the graph. Someone who cannot
 * separate the two golds still reads the same graph.
 *
 * The highlight uses `--brand` rather than `--accent`. In this design system
 * `--accent` resolves to `--brand-subtle`, a pale background tint — correct for
 * filling a chip, invisible as a 2px stroke on a 1px diagram.
 *
 * The panel is not decoration either. A diagram that showed only the winner
 * would be a diagram that cannot be disagreed with; listing every cause with the
 * probability it ended up at is what makes the conclusion checkable.
 */

import { useMemo } from "react";
import dagre from "@dagrejs/dagre";
import {
  Background,
  Controls,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { CaseDag, CausalDagNode } from "@/lib/api/dag";
import { formatPercent } from "@/lib/utils/format";
import { cn } from "@/lib/utils/cn";

/** Node box size. Dagre needs real numbers before anything is rendered. */
const NODE_WIDTH = 210;
const NODE_HEIGHT = 56;

type NodeData = {
  label: string;
  description: string;
  /** Observables: whether the fact was true, false, or never established. */
  observed?: boolean | null;
  /** Root causes: the posterior it settled at. */
  probability?: number | null;
  onPath: boolean;
  isWinner: boolean;
};

function ObservableNode({ data }: NodeProps) {
  const { label, description, observed, onPath } = data as unknown as NodeData;

  return (
    <div
      title={description || label}
      className={cn(
        "flex h-[56px] w-[210px] items-center gap-2 rounded-md border bg-elevated px-3 py-2 text-left",
        onPath ? "border-2 border-brand" : "border-edge",
        observed === false && "opacity-55",
      )}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <span
        aria-hidden
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          observed === true ? "bg-brand" : observed === false ? "bg-ink-faint" : "bg-transparent",
        )}
      />
      <div className="min-w-0">
        <div className="truncate text-[11px] leading-tight font-medium text-ink">{label}</div>
        <div className="text-[10px] text-ink-faint">
          {observed === true ? "observed" : observed === false ? "checked — absent" : "not checked"}
        </div>
      </div>
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}

function RootCauseNode({ data }: NodeProps) {
  const { label, description, probability, isWinner, onPath } = data as unknown as NodeData;

  return (
    <div
      title={description || label}
      className={cn(
        "flex h-[56px] w-[210px] items-center justify-between gap-2 rounded-4xl border px-3.5 py-2",
        isWinner
          ? "border-brand bg-brand text-brand-foreground"
          : onPath
            ? "border-2 border-brand bg-brand-subtle text-brand"
            : "border-hairline bg-subtle text-ink-muted opacity-70",
      )}
    >
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <span className="min-w-0 truncate text-[11px] leading-tight font-medium">{label}</span>
      {probability != null ? (
        <span className="shrink-0 font-mono text-[11px] tabular-nums">
          {formatPercent(probability, 0)}
        </span>
      ) : null}
      <Handle type="source" position={Position.Right} className="!opacity-0" />
    </div>
  );
}

const NODE_TYPES = { observable: ObservableNode, rootCause: RootCauseNode };

/**
 * Run dagre over the graph and hand back positioned nodes.
 *
 * Rank direction is left-to-right, and the *edges are reversed* going in:
 * the graph's arrows run cause → symptom, but the story runs symptom → cause,
 * so laying it out in the arrow direction would put every conclusion on the
 * left and read backwards.
 */
function layout(dag: CaseDag, path: Set<string>, winner: string | null): [Node[], Edge[]] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 14, ranksep: 120, marginx: 12, marginy: 12 });

  for (const node of dag.nodes) {
    graph.setNode(node.node_id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of dag.edges) {
    graph.setEdge(edge.to, edge.from);
  }
  dagre.layout(graph);

  const observed = dag.traversal?.observed_features ?? {};
  const posteriors = dag.traversal?.posteriors ?? {};

  const nodes: Node[] = dag.nodes.map((node: CausalDagNode) => {
    const position = graph.node(node.node_id);
    return {
      id: node.node_id,
      type: node.node_type === "root_cause" ? "rootCause" : "observable",
      position: {
        x: (position?.x ?? 0) - NODE_WIDTH / 2,
        y: (position?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: {
        label: node.label,
        description: node.description,
        observed: node.node_id in observed ? observed[node.node_id] : null,
        probability: node.node_type === "root_cause" ? (posteriors[node.node_id] ?? null) : null,
        onPath: path.has(node.node_id),
        isWinner: node.node_id === winner,
      } satisfies NodeData,
      draggable: false,
      connectable: false,
    };
  });

  const edges: Edge[] = dag.edges.map((edge) => {
    // An edge is on the path when it runs from the diagnosed cause to a symptom
    // that actually fired. That is narrower than "both ends are highlighted" —
    // it is the set of arrows that did the explaining.
    const onPath = edge.from === winner && path.has(edge.to);
    return {
      id: `${edge.from}->${edge.to}`,
      source: edge.to,
      target: edge.from,
      animated: onPath,
      label: `${Math.round(edge.likelihood * 100)}%`,
      labelShowBg: false,
      labelStyle: { fill: "var(--text-tertiary)", fontSize: 9 },
      style: {
        stroke: onPath ? "var(--brand)" : "var(--border-strong)",
        strokeWidth: onPath ? 2 : 1,
        opacity: onPath ? 1 : 0.35,
      },
    };
  });

  return [nodes, edges];
}

function PosteriorPanel({ dag }: { dag: CaseDag }) {
  const posteriors = dag.traversal?.posteriors ?? {};
  const winner = dag.traversal?.root_cause;
  const labels = new Map(dag.nodes.map((node) => [node.node_id, node.label]));

  const ranked = Object.entries(posteriors).sort(([, a], [, b]) => b - a);

  return (
    <div className="space-y-2">
      <h3 className="text-[10px] font-medium tracking-[0.06em] text-ink-faint uppercase">
        What else it could be
      </h3>
      <ul className="space-y-1.5">
        {ranked.map(([nodeId, probability]) => (
          <li key={nodeId}>
            <div className="flex items-baseline justify-between gap-2">
              <span
                className={cn(
                  "truncate text-[11px]",
                  nodeId === winner ? "font-medium text-ink" : "text-ink-muted",
                )}
              >
                {labels.get(nodeId) ?? nodeId}
              </span>
              <span className="shrink-0 font-mono text-[11px] tabular-nums text-ink-muted">
                {formatPercent(probability, 1)}
              </span>
            </div>
            <div className="mt-0.5 h-1 rounded-full bg-subtle">
              <div
                className={cn("h-full rounded-full", nodeId === winner ? "bg-brand" : "bg-edge")}
                // A floor of 1% so a cause the evidence crushed is still a
                // visible sliver rather than an empty row that reads as a
                // rendering fault.
                style={{ width: `${Math.max(1, probability * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function CausalDagViewer({ dag }: { dag: CaseDag }) {
  const traversal = dag.traversal;
  const path = useMemo(() => new Set(traversal?.causal_path ?? []), [traversal]);
  const winner = traversal?.root_cause ?? null;

  const [nodes, edges] = useMemo(() => layout(dag, path, winner), [dag, path, winner]);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_240px]">
      {/* React Flow measures its container, so the height has to be explicit —
          a percentage of an auto-height parent computes to zero and the canvas
          renders blank with no error. */}
      <div className="h-[520px] overflow-hidden rounded-lg border border-hairline bg-base">
        <ReactFlowProvider>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            fitView
            fitViewOptions={{ padding: 0.12 }}
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            // The graph is a diagram, not an editor. Zoom on scroll would trap
            // the page scroll the moment a reader's cursor crossed it.
            zoomOnScroll={false}
            panOnScroll
            minZoom={0.3}
            maxZoom={1.6}
          >
            <Background color="var(--border-subtle)" gap={18} size={1} />
            <Controls showInteractive={false} className="!shadow-none" />
          </ReactFlow>
        </ReactFlowProvider>
      </div>

      <div className="space-y-4">
        {traversal ? (
          <div className="rounded-lg border border-hairline p-3">
            <div className="text-[10px] tracking-[0.06em] text-ink-faint uppercase">Diagnosed</div>
            <div className="mt-0.5 text-sm font-medium text-ink">
              {dag.nodes.find((node) => node.node_id === traversal.root_cause)?.label ??
                traversal.root_cause}
            </div>
            <div className="mt-1 font-mono text-2xl tabular-nums text-brand">
              {formatPercent(traversal.posterior_probability, 0)}
            </div>
            <p className="mt-2 text-[11px] leading-relaxed text-ink-muted">
              Computed from {Object.keys(traversal.observed_features).length} checked facts
              against graph {dag.dag_version}. The same evidence always gives the same answer.
            </p>
          </div>
        ) : null}

        <PosteriorPanel dag={dag} />
      </div>
    </div>
  );
}

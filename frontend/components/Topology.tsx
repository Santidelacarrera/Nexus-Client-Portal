"use client";
import ReactFlow, { Background, Edge, MarkerType, Node } from "reactflow";

const base = { background: "#0b1220", color: "#e2e8f0", fontFamily: "JetBrains Mono, monospace", fontSize: 11, borderRadius: 6, padding: 8, width: 150, textAlign: "center" as const };
const border = (c: string) => ({ ...base, border: `1px solid ${c}`, boxShadow: `0 0 14px -4px ${c}` });

export function Topology({ degraded }: { degraded: boolean }) {
  const nodes: Node[] = [
    { id: "client", position: { x: 0, y: 70 }, data: { label: "Your estate" }, style: border("#334155"), draggable: false },
    { id: "shadow", position: { x: 220, y: 0 }, data: { label: "ShadowAPI_Guard" }, style: border(degraded ? "#f59e0b" : "#06b6d4"), draggable: false },
    { id: "kube", position: { x: 220, y: 70 }, data: { label: "KubeCost_Auto_HPA" }, style: border("#10b981"), draggable: false },
    { id: "rag", position: { x: 220, y: 140 }, data: { label: "ContextRAG_Engine" }, style: border("#06b6d4"), draggable: false },
    { id: "consensus", position: { x: 440, y: 70 }, data: { label: "MultiAgent_Consensus" }, style: border("#22d3ee"), draggable: false },
    { id: "report", position: { x: 660, y: 70 }, data: { label: "Signed report" }, style: border("#10b981"), draggable: false },
  ];
  const e = (s: string, t: string, color = "#475569"): Edge => ({ id: `${s}-${t}`, source: s, target: t, animated: true, style: { stroke: color }, markerEnd: { type: MarkerType.ArrowClosed, color } });
  const edges = [e("client", "shadow"), e("client", "kube"), e("client", "rag"), e("shadow", "consensus", "#06b6d4"), e("kube", "consensus", "#10b981"), e("rag", "consensus", "#06b6d4"), e("consensus", "report", "#10b981")];
  return (
    <div className="h-[230px] w-full" role="img" aria-label="Service topology: client estate to agents to consensus to signed report">
      <ReactFlow nodes={nodes} edges={edges} fitView nodesConnectable={false} elementsSelectable={false} panOnDrag={false} zoomOnScroll={false} zoomOnDoubleClick={false} proOptions={{ hideAttribution: true }}>
        <Background color="#1f2937" gap={20} />
      </ReactFlow>
    </div>
  );
}

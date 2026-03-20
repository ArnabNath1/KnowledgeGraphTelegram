"""
Graph Visualization Service
Generates beautiful interactive HTML graphs using pyvis + static PNG using networkx/matplotlib
"""
import os
import json
import uuid
from pathlib import Path
from typing import Any, Optional
from loguru import logger

from config import get_settings

settings = get_settings()

# Color palette for concept types
TYPE_COLORS = {
    "ALGORITHM": "#6C63FF",
    "THEORY": "#FF6B6B",
    "METHOD": "#4ECDC4",
    "DATASET": "#45B7D1",
    "VARIABLE": "#96CEB4",
    "ENTITY": "#FFEAA7",
    "INSTITUTION": "#DDA0DD",
    "AUTHOR": "#98D8C8",
    "DOMAIN": "#F7DC6F",
    "METRIC": "#82E0AA",
    "DEFAULT": "#AEB6BF",
}

# Relationship colors
REL_COLORS = {
    "CAUSES": "#E74C3C",
    "DEPENDS_ON": "#3498DB",
    "IMPROVES": "#2ECC71",
    "CONTRADICTS": "#E67E22",
    "DERIVED_FROM": "#9B59B6",
    "USES_DATASET": "#1ABC9C",
    "SIMILAR_TO": "#F1C40F",
    "EVALUATES": "#2980B9",
    "PROPOSES": "#8E44AD",
    "APPLIES_TO": "#27AE60",
    "PART_OF": "#D35400",
    "RELATED_TO": "#7F8C8D",
}


class VisualizationService:
    """Creates graph visualizations"""

    def __init__(self):
        self.output_dir = Path(settings.graph_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Visualization output dir: {self.output_dir}")

    def get_node_color(self, node_type: str) -> str:
        return TYPE_COLORS.get(node_type.upper() if node_type else "", TYPE_COLORS["DEFAULT"])

    def get_edge_color(self, rel_type: str) -> str:
        if rel_type:
            for key in REL_COLORS:
                if key in rel_type.upper():
                    return REL_COLORS[key]
        return REL_COLORS["RELATED_TO"]

    async def generate_pyvis_html(
        self,
        user_id: int,
        nodes: list[dict],
        relationships: list[dict],
        title: str = "Knowledge Graph",
    ) -> Optional[str]:
        """Generate interactive pyvis HTML graph"""
        try:
            from pyvis.network import Network

            net = Network(
                height="750px",
                width="100%",
                bgcolor="#1a1a2e",
                font_color="#e0e0e0",
                directed=True,
                notebook=False,
            )
            net.set_options(json.dumps({
                "nodes": {
                    "borderWidth": 2,
                    "shadow": True,
                    "font": {"size": 14, "color": "#ffffff"},
                },
                "edges": {
                    "arrows": {"to": {"enabled": True, "scaleFactor": 1}},
                    "smooth": {"type": "curvedCW", "roundness": 0.2},
                    "font": {"size": 10, "color": "#cccccc", "align": "middle"},
                    "shadow": True,
                },
                "physics": {
                    "enabled": True,
                    "solver": "forceAtlas2Based",
                    "forceAtlas2Based": {
                        "gravitationalConstant": -80,
                        "centralGravity": 0.01,
                        "springLength": 150,
                        "springConstant": 0.08,
                    },
                    "stabilization": {"iterations": 150},
                },
                "interaction": {
                    "hover": True,
                    "navigationButtons": True,
                    "keyboard": True,
                },
            }))

            # Add nodes
            node_names = set()
            for node in nodes:
                name = node.get("name", "")
                if not name or name in node_names:
                    continue
                node_names.add(name)
                importance = node.get("importance", 5)
                node_type = node.get("type", "ENTITY")
                color = self.get_node_color(node_type)
                size = 15 + importance * 3
                net.add_node(
                    name,
                    label=name,
                    title=f"<b>{name}</b><br>Type: {node_type}<br>{node.get('description', '')}",
                    color={"background": color, "border": "#ffffff", "highlight": {"background": color, "border": "#FFD700"}},
                    size=size,
                    shape="dot",
                )

            # Add edges
            for rel in relationships:
                src = rel.get("source", "")
                tgt = rel.get("target", "")
                if not src or not tgt or src not in node_names or tgt not in node_names:
                    continue
                relation = rel.get("relation", "RELATED_TO").replace("_", " ")
                color = self.get_edge_color(rel.get("relation", ""))
                conf = rel.get("confidence", 0.8)
                net.add_edge(
                    src, tgt,
                    label=relation.lower(),
                    title=rel.get("description", relation),
                    color={"color": color, "opacity": 0.7},
                    width=1 + conf * 2,
                    arrows="to",
                )

            # Save HTML
            graph_id = f"u{user_id}_{uuid.uuid4().hex[:8]}"
            filepath = self.output_dir / f"{graph_id}.html"

            # Custom HTML template with title
            net.write_html(str(filepath))
            # Inject custom title + styles into HTML
            html = filepath.read_text(encoding="utf-8")
            html = html.replace(
                "<title>PyVis</title>",
                f"<title>{title}</title>",
            )
            # Add legend
            legend_html = self._build_legend_html()
            html = html.replace("</body>", f"{legend_html}</body>")
            filepath.write_text(html, encoding="utf-8")

            logger.success(f"Generated pyvis graph: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"Pyvis generation failed: {e}")
            return None

    async def generate_png(
        self,
        user_id: int,
        nodes: list[dict],
        relationships: list[dict],
        title: str = "Knowledge Graph",
    ) -> Optional[str]:
        """Generate static PNG using networkx + matplotlib"""
        try:
            import networkx as nx
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.patches as mpatches

            G = nx.DiGraph()

            # Add nodes
            for node in nodes:
                name = node.get("name", "")
                if name:
                    G.add_node(
                        name,
                        node_type=node.get("type", "ENTITY"),
                        importance=node.get("importance", 5),
                    )

            # Add edges
            for rel in relationships:
                src = rel.get("source", "")
                tgt = rel.get("target", "")
                if src and tgt and G.has_node(src) and G.has_node(tgt):
                    G.add_edge(src, tgt, relation=rel.get("relation", "RELATED_TO"))

            if len(G.nodes) == 0:
                return None

            # Layout
            if len(G.nodes) < 10:
                pos = nx.spring_layout(G, seed=42, k=2)
            elif len(G.nodes) < 30:
                pos = nx.kamada_kawai_layout(G)
            else:
                pos = nx.spring_layout(G, seed=42, k=1.5, iterations=50)

            fig, ax = plt.subplots(1, 1, figsize=(16, 10))
            fig.patch.set_facecolor("#1a1a2e")
            ax.set_facecolor("#16213e")

            # Draw edges
            node_colors = [self.get_node_color(G.nodes[n].get("node_type", "ENTITY")) for n in G.nodes]
            node_sizes = [300 + G.nodes[n].get("importance", 5) * 100 for n in G.nodes]

            nx.draw_networkx_edges(
                G, pos, ax=ax,
                arrowsize=20,
                edge_color="#4a4a8a",
                alpha=0.6,
                arrows=True,
                connectionstyle="arc3,rad=0.1",
            )
            nx.draw_networkx_nodes(
                G, pos, ax=ax,
                node_color=node_colors,
                node_size=node_sizes,
                alpha=0.9,
            )
            nx.draw_networkx_labels(
                G, pos, ax=ax,
                font_size=8,
                font_color="white",
                font_weight="bold",
            )

            # Edge labels (just first 20)
            edge_labels = {
                (u, v): G[u][v]["relation"].replace("_", " ").lower()
                for u, v in list(G.edges)[:20]
            }
            nx.draw_networkx_edge_labels(
                G, pos, ax=ax,
                edge_labels=edge_labels,
                font_size=6,
                font_color="#aaaaaa",
            )

            # Legend
            patches = [
                mpatches.Patch(color=color, label=t)
                for t, color in list(TYPE_COLORS.items())[:8]
            ]
            ax.legend(handles=patches, loc="upper left", framealpha=0.3,
                     labelcolor="white", facecolor="#1a1a2e", fontsize=8)

            ax.set_title(title, color="white", fontsize=14, fontweight="bold", pad=20)
            ax.axis("off")
            plt.tight_layout()

            graph_id = f"u{user_id}_{uuid.uuid4().hex[:8]}"
            filepath = self.output_dir / f"{graph_id}.png"
            plt.savefig(str(filepath), dpi=150, bbox_inches="tight",
                       facecolor=fig.get_facecolor())
            plt.close()

            logger.success(f"Generated PNG graph: {filepath}")
            return str(filepath)
        except Exception as e:
            logger.error(f"PNG generation failed: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _build_legend_html(self) -> str:
        """Build HTML legend for pyvis graph"""
        items = "".join(
            f'<span style="background:{color};padding:2px 8px;border-radius:4px;margin:2px;display:inline-block;font-size:11px">{t}</span>'
            for t, color in list(TYPE_COLORS.items())[:8]
        )
        return f"""
        <div style="position:fixed;bottom:20px;left:20px;background:rgba(0,0,0,0.7);
                    padding:10px;border-radius:8px;color:white;font-family:sans-serif;font-size:12px;z-index:1000">
            <b>Node Types:</b><br>{items}
        </div>"""

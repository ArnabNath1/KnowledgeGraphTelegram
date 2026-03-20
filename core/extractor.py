"""
Concept Extraction Engine using Groq LLM
Extracts: Entities, Topics, Methods, Theories, Variables, Datasets, Algorithms
and their relationships from research text.
"""
import json
import re
from typing import Any
from loguru import logger
from groq import AsyncGroq
from config import get_settings

settings = get_settings()

CONCEPT_EXTRACTION_PROMPT = """You are an elite research knowledge extraction AI.
Analyze the following research text and extract a structured knowledge graph.

Extract:
1. **Concepts/Entities** - key topics, theories, methods, algorithms, datasets, variables, authors, institutions
2. **Relationships** - how concepts connect (causes, depends_on, improves, contradicts, derived_from, uses_dataset, similar_to, evaluates, proposes, applies_to, part_of, related_to)

Return STRICTLY valid JSON (no markdown, no extra text) in this exact format:
{{
  "concepts": [
    {{
      "name": "concept name",
      "type": "ALGORITHM|THEORY|METHOD|DATASET|VARIABLE|ENTITY|INSTITUTION|AUTHOR|DOMAIN|METRIC",
      "description": "brief 1-sentence description",
      "importance": 1-10
    }}
  ],
  "relationships": [
    {{
      "source": "concept name",
      "target": "concept name",
      "relation": "relation_type",
      "description": "brief description of relationship",
      "confidence": 0.0-1.0
    }}
  ],
  "summary": "2-3 sentence summary of the text",
  "domain": "primary research domain"
}}

Research Text:
{text}

Return ONLY the JSON object. No markdown fences, no explanation.
If no concepts are found, you MUST still return a valid JSON object with empty lists:
{"concepts": [], "relationships": [], "summary": "...", "domain": "..."}"""


RESEARCH_GAP_PROMPT = """You are a senior research analyst specializing in identifying research gaps.

Given this knowledge graph data:
- Nodes (concepts): {nodes}
- Relationships: {relationships}
- Research domain: {domain}

Analyze and identify research gaps. Return STRICTLY valid JSON:
{{
  "gaps": [
    {{
      "title": "Gap title",
      "description": "Detailed description",
      "connected_concepts": ["concept1", "concept2"],
      "importance": "HIGH|MEDIUM|LOW",
      "suggestion": "Specific research suggestion"
    }}
  ],
  "weak_connections": ["concept1 <-> concept2", ...],
  "isolated_concepts": ["concept that needs more connections"],
  "novelty_score": 0.0-1.0,
  "overall_assessment": "Overall assessment of knowledge coverage"
}}"""


PATH_EXPLANATION_PROMPT = """You are a research knowledge explainer.

Given a concept path in a knowledge graph:
Source: {source}
Target: {target}
Path: {path}
Context: {context}

Explain the reasoning chain connecting {source} to {target} through this path.
Make it educational, precise and research-level.

Return JSON:
{{
  "explanation": "Full reasoning chain explanation",
  "steps": [
    {{"from": "concept", "to": "concept", "via": "relationship", "reasoning": "why this connection matters"}}
  ],
  "key_insight": "The most important insight from this path",
  "applications": ["practical application 1", "practical application 2"]
}}"""


class ConceptExtractor:
    """Extracts concepts and relationships from text using Groq LLM"""

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.groq_model
        logger.info(f"ConceptExtractor initialized with model: {self.model}")

    async def extract(self, text: str) -> dict[str, Any]:
        """Extract concepts and relationships from research text."""
        if len(text) > 10000:
            chunks = self._chunk_text(text, max_chars=8000)
            results = []
            for i, chunk in enumerate(chunks):
                logger.info(f"Processing chunk {i+1}/{len(chunks)}")
                result = await self._extract_single(chunk)
                results.append(result)
            return self._merge_results(results)
        else:
            return await self._extract_single(text)

    async def _extract_single(self, text: str) -> dict[str, Any]:
        """Extract from a single text chunk"""
        raw = ""
        try:
            prompt = CONCEPT_EXTRACTION_PROMPT.format(text=text)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4096,
            )
            raw = response.choices[0].message.content.strip()
            
            # Robust JSON extraction
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if not match:
                logger.error(f"No JSON found in LLM response: {raw[:200]}")
                return self._empty_result()
            
            json_str = match.group(1)
            data = json.loads(json_str)
            
            if not isinstance(data, dict):
                return self._empty_result()
            
            # Ensure keys exist 
            res = {
                "concepts": data.get("concepts", []),
                "relationships": data.get("relationships", []),
                "domain": data.get("domain", "Research"),
                "summary": data.get("summary", "Extracted content summary"),
            }
            logger.success(f"Extracted {len(res['concepts'])} nodes from chunk")
            return res
            
        except Exception as e:
            logger.error(f"Extraction error: {e}")
            return self._empty_result()

    async def find_research_gaps(self, nodes: list, relationships: list, domain: str) -> dict[str, Any]:
        try:
            prompt = RESEARCH_GAP_PROMPT.format(
                nodes=json.dumps(nodes[:40], indent=2),
                relationships=json.dumps(relationships[:60], indent=2),
                domain=domain,
            )
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, max_tokens=3000,
            )
            raw = response.choices[0].message.content.strip()
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return {"gaps": [], "overall_assessment": "Failure"}
        except Exception as e:
            logger.error(f"Gap error: {e}")
            return {"gaps": [], "overall_assessment": str(e)}

    async def explain_path(self, source: str, target: str, path: list, context: str = "") -> dict[str, Any]:
        try:
            prompt = PATH_EXPLANATION_PROMPT.format(source=source, target=target, path=" -> ".join(path), context=context)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4, max_tokens=2000,
            )
            raw = response.choices[0].message.content.strip()
            match = re.search(r"(\{.*\})", raw, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return {"explanation": "Explanation failed"}
        except Exception as e:
            logger.error(f"Path error: {e}")
            return {"explanation": "Error: " + str(e)}

    def _chunk_text(self, text: str, max_chars: int = 8000) -> list[str]:
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) < max_chars:
                current += para + "\n\n"
            else:
                if current: chunks.append(current.strip())
                current = para + "\n\n"
        if current: chunks.append(current.strip())
        return chunks if chunks else [text[:max_chars]]

    def _merge_results(self, results: list[dict]) -> dict[str, Any]:
        merged_concepts, merged_relationships = {}, []
        domains, summaries = [], []
        for r in results:
            for c in r.get("concepts", []):
                name = c.get("name", "").lower()
                if name and name not in merged_concepts: merged_concepts[name] = c
            merged_relationships.extend(r.get("relationships", []))
            if r.get("domain"): domains.append(r["domain"])
            if r.get("summary"): summaries.append(r["summary"])
        return {
            "concepts": list(merged_concepts.values()),
            "relationships": merged_relationships,
            "domain": domains[0] if domains else "Research",
            "summary": " ".join(summaries[:3]),
        }

    def _empty_result(self) -> dict[str, Any]:
        return {"concepts": [], "relationships": [], "domain": "Unknown", "summary": "Failed"}

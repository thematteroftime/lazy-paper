SYSTEM:
You are a careful materials-science research assistant. Read a paper's abstract and introduction and return STRICT YAML (no markdown fence) describing the paper. Output ONLY the YAML; no preamble.

USER:
Abstract and introduction of the paper follow between <<< >>> markers.

<<<
{paper_text}
>>>

Return YAML with this exact schema:
title: <one-line English title>
system: <chemical formula or short system descriptor, e.g. "Ag(1-3x)La(x)Nb(0.9)Ta(0.1)O3 ceramics">
abbreviations:
  - {abbr: <abbr>, expansion: <full term>}
key_terms:
  - <term>
keywords:
  - <keyword>
critical_questions:
  - <one open question raised by the paper>

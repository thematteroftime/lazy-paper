SYSTEM:
You are a careful scientific research assistant. Read a paper's abstract and introduction and return STRICT YAML (no markdown fence) describing the paper. Output ONLY the YAML; no preamble.

USER:
Abstract and introduction of the paper follow between <<< >>> markers.

<<<
{paper_text}
>>>

Return YAML with this exact schema:
title: <one-line English title>
system: >-
  <Specific system or domain being studied; for materials use chemical formula, for other domains use the architecture/method name (e.g., 'ResNet-50 on ImageNet', 'unCLIP with diffusion prior').
   GOOD (materials): "(Pb0.94-xCdxLa0.04)(Hf0.7Sn0.3)O3 ceramics"
   GOOD (materials): "flash-heat-crystallized PbZrO3/LSMO/SRO heterostructure films"
   GOOD (ML): "ResNet-50 on ImageNet", "unCLIP with diffusion prior"
   BAD: "PbZrO3 film" (omits heterostructure/processing), "energy storage ceramic" (no formula)
   e.g. "Ag(1-3x)La(x)Nb(0.9)Ta(0.1)O3 ceramics">
abbreviations:
  - {abbr: <abbr>, expansion: <full term>}
key_terms:
  - <term>
keywords:
  - <keyword>
critical_questions:
  - <one open question raised by the paper>

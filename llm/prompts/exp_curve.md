SYSTEM:
You are analyzing ONE experiment plot from the user's own research (training curve, metric-vs-time, ablation bar chart, etc.). Return STRICT YAML only (no fence, no preamble):

visual_summary: >-
  <axes, units, ranges, every distinguishable series, crossing/inflection points — concrete numbers read off the plot>
deep_observation: >-
  <what the trend MEANS for the experiment: convergence/divergence, regressions vs expectations, regime changes, suspicious flat/spiky segments>
anomalies:
  - <each anomaly worth the researcher's attention, with the approximate x/y location; empty list if none>

Rules: read numbers off the axes wherever legible; never invent values you cannot see; {lang_instruction}

USER:
Experiment context (from exp.yaml):
<<<
{exp_context}
>>>
Analyze the attached plot.

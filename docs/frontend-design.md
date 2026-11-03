# Design contract
Reference: ranjithrd/caduceus, inspected at b625070. Reference is used for frontend design only.

Palette: canvas #FFFFFF; text #1D1D1F; secondary #86868B; dividers #D2D2D7; change #FF3B30; action #0071E3.
Type: Helvetica Neue, Helvetica, Arial. 56px gene/variant hero; 30px page title; 19px list rows; 14–16px supporting text.
Layout: 980px centred shell, left-aligned content, generous white space, thin list dividers, 56px desktop column gap, quiet 320px context column. Stack below 860px.

Home                 Gene / queue                  Variant
search               title + release               back + identity
BRCA1     count      variants | context             release selector
BRCA2     count      thin rows | history             state timeline
TP53      count      change bars                    assertions | provenance

Review against brief: keep the reference's flat white lists and typography. Do not invent a dashboard card grid, dark hero, new typefaces or decorative gradients. Replace cancer-cohort content with ClinVar genes, observed releases and submission histories. A release timeline is the primary interaction, not a decorative statistic. Source and pending-outcome states must be explicit. Add focus states, mobile layouts and reduced-motion handling.

Release-switching revision: retain the palette, Helvetica hierarchy and list layout
above. Keep the release control mounted during variant requests and errors; carry
its URL parameter across primary navigation and return links. The timeline offers
all accepted releases but reveals classification states only through the selected
release. Later links say “View release”, preserving the historical-view contract.
Gene lists reset filters and pagination together on a release/gene change.

All accepted months now appear as wrapped buttons in a persistent site-wide
release strip. Selecting an older snapshot does not hide later navigation tabs.
The variant history also wraps rather than clipping months offscreen. A failed
catalogue refresh retains the last successful list. Audit and model pages explain
classification-change ranking, identify fixed baselines versus learned methods,
and distinguish saved evaluation results from archive imports. No-change runs
explicitly state that all-zero scores provide no useful priority order.

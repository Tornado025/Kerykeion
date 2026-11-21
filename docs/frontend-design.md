# Design contract
Reference: ranjithrd/caduceus, inspected at b625070. Reference is used for frontend design only.

Palette: canvas #FFFFFF; text #1D1D1F; secondary #86868B; dividers #D2D2D7; change #FF3B30; action #0071E3.
Type: Helvetica Neue, Helvetica, Arial. 56px gene/variant hero; 30px page title; 19px list rows; 14–16px supporting text.
Layout: 980px centred shell, left-aligned content, generous white space, thin list dividers, 56px desktop column gap, quiet 320px context column. Stack below 860px.

Home                 Gene / queue                  Variant
latest data month    latest data month             latest data month
search               variants | context             identity + current state
BRCA1     count      filters and review queue       optional classification history
BRCA2     count      optional historical selection  assertions | provenance
TP53      count

## Latest data by default

Normal browsing opens the most recent accepted release, currently November 2026.
The site-wide month-button strip is removed. A quiet snapshot row shows Latest
data and the month, with View historical release as a secondary action. That
action opens one compact dropdown; it does not add another row of month tabs.

Explicit historical URLs remain valid. Show Historical view, the selected month,
and Return to latest. The latest option removes the explicit release and model
parameters while preserving page-specific identity and other filters. Normal
primary navigation follows the latest data; historical navigation carries its
selected release. The snapshot control stays mounted during data requests and
errors. Failed catalogue refreshes retain the last successful list.

On variant pages, Classification history is collapsed initially. Opening it shows
the existing timeline and links to other releases. Classifications from after the
selected release remain hidden; their links only invite the user to view that
release. Gene pagination and filters reset when the selected snapshot changes.

## Visual treatment

Retain the flat white lists, Helvetica hierarchy, grey dividers and restrained blue
actions. The snapshot row is compact supporting context, not a dashboard card or
hero. On narrow screens its status and actions stack; labels and controls wrap
without horizontal scrolling. The history disclosure uses a thin divider and no
extra decorative containers. Focus styles and reduced-motion preferences remain.

Prediction pages identify their forecast origin and horizon explicitly. Do not
silently use an older model if a forecast for the latest release is unavailable.
Comparison methods, earlier endpoint experiments and detailed model inputs stay
available on demand. No-change scores explain their lack of priority ordering.
Classification-change forecasts do not imply a clinical diagnosis.

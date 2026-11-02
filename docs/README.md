# Project documentation

The latest approved coursework deliverables are in [deliverables](deliverables/):

- [ER diagram and explanation](deliverables/01_ER_Diagram_and_Explanation.pdf)
- [ER-to-relational mapping — colour](deliverables/02a_Relational_Schema_Colour.pdf)
- [ER-to-relational mapping — black arrows](deliverables/02b_Relational_Schema_Black.pdf)
- [Integrated data-flow diagrams](deliverables/03_DFD_Yourdon_DeMarco.pdf)
- [Normalization through BCNF](deliverables/04_Normalization.pdf)
- [Combined editable draw.io workbook](deliverables/ClinVar_All_Diagrams.drawio)
- [Detailed project defence and speaking script](deliverables/ClinVar_Detailed_Project_Defence_and_Speaking_Script.pdf)
- [Implementation plan](deliverables/Implementation_Plan.pdf), also in [Markdown](deliverables/Implementation_Plan.md)

See [physical design decisions](decisions.md) for implementation refinements relative to the coursework diagrams, including model-independent outcomes, and [frontend design](frontend-design.md) for the caduceus reference contract.

## Demo checkpoint

Implementation is in progress. January and February 2025 real ClinVar extracts were accepted for the three-gene cohort; March preparation was interrupted when work was paused. React, TypeScript, Vite, FastAPI, PostgreSQL, MongoDB and Neo4j are integrated locally. Local archive extracts, database volumes, fitted models, environment files and verification artifacts are intentionally not committed.

At the last verified checkpoint: 11 backend/cross-store integration tests and 3 frontend tests passed. These include synthetic, clearly tagged test fixtures and do not establish full scientific validation. Historical projection replay and real-data scoring were exercised; the small demo and wider evaluation remain in progress. Consult the root README to reproduce the data rather than assuming it ships in Git.

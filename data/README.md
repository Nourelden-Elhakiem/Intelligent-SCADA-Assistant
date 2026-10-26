# Data Management

The Intelligent SCADA Assistant uses a structured pipeline for PDF ingestion, image extraction, semantic chunking, vector embeddings, and retrieval.

### Data Architecture
- **Local processing:** Organized storage for PDFs, images, text, manifests, and embeddings.
- **API processing:** Isolated document storage under `data/documents/<document-key>/`.
- **Data integrity:** Artifact validation and reproducible processing.

> [!NOTE]
> Development uses `Power SCADA Operation 2020 System Guide.pdf` as the reference manual.


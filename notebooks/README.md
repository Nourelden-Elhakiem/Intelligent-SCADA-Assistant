# Research Notebooks

Eight numbered notebooks preserve the project's research lineage and integrate with the production `intelligent_scada` package. Notebooks 01–07 represent the original processing sequence, while notebook 08 demonstrates the end-to-end production pipeline.

## Notebook Overview

- [01_image_extraction_and_filtering](01_image_extraction_and_filtering.ipynb)
- [02_pdf_structure_exploration](02_pdf_structure_exploration.ipynb)
- [03_text_extraction_and_cleaning](03_text_extraction_and_cleaning.ipynb)
- [04_toc_aware_chunking](04_toc_aware_chunking.ipynb)
- [05_image_text_linking](05_image_text_linking.ipynb)
- [06_embedding_generation](06_embedding_generation.ipynb)
- [07_database_ingestion_and_indexing](07_database_ingestion_and_indexing.ipynb)
- [08_prepare_power_scada_manual](08_prepare_power_scada_manual.ipynb) — End-to-end production walkthrough.

## Pipeline Integration

Notebooks 01–06 demonstrate individual processing modules and generate exploratory artifacts.

Notebook 07 integrates with `Pipeline.ingest`, supporting resumable processing, artifact provenance validation, and transactional database indexing. Valid manual image-review decisions are preserved unless a forced rebuild is requested.

Notebook 08 executes the production ingestion and retrieval workflow. External provider testing remains disabled unless `RUN_PROVIDER_SMOKE` is explicitly enabled.

Notebook configuration supports `.env` reloading through `env_override=True` and external PDF paths through `SCADA_DEFAULT_PDF_PATH`.

## Research Lineage

The published notebooks contain no execution outputs or execution counts. Historical Git commits preserve the original research progression, including historical notebook outputs.

The legacy pipeline diagram documents the original research workflow rather than the current production database architecture.

[Historical Notebook Pipeline Diagram](../docs/diagrams/notebook_data_pipeline_overview.png)

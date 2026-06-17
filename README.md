# Intelligent SCADA Assistant

An experimental AI assistant for SCADA technical manuals, built around a notebook-based Retrieval-Augmented Generation (RAG) pipeline.

The project focuses on transforming complex industrial documentation into a structured, searchable, and retrieval-ready knowledge base using text extraction, document chunking, semantic embeddings, PostgreSQL, and pgvector.

> Current Status: Notebook-based research and prototyping phase.
> Future Goal: Refactor the project into a clean production-ready AI application with a backend API, retrieval service, and user interface.

---

## Project Overview

SCADA manuals and industrial technical documents are usually large, dense, and difficult to search manually. Engineers often need quick access to precise procedures, configuration details, troubleshooting steps, and visual references.

This project explores how AI and semantic retrieval can support technical documentation search by building a pipeline that:

* Extracts text from technical PDF manuals.
* Cleans and structures document content.
* Splits the document into meaningful chunks based on the table of contents.
* Generates semantic embeddings for each chunk.
* Stores chunks and embeddings in PostgreSQL with pgvector.
* Links relevant extracted images to nearby text sections.
* Prepares the knowledge base for future RAG-based question answering.

---

## Key Features

* PDF text extraction and cleaning
* PDF structure and table-of-contents exploration
* TOC-aware semantic chunking
* Image extraction and filtering
* Image-to-text chunk linking
* Sentence-transformer embedding generation
* PostgreSQL database ingestion
* pgvector-based semantic search preparation
* Metadata-rich chunks for better citations and traceability
* Notebook-based experimentation workflow

---

## Repository Structure

```text
Intelligent-SCADA-Assistant/
│
├── docs/
│   └── diagrams/
│       └── notebook_data_pipeline_overview.png
│
├── notebooks/
│   ├── 01_image_extraction_and_filtering.ipynb
│   ├── 02_pdf_structure_exploration.ipynb
│   ├── 03_text_extraction_and_cleaning.ipynb
│   ├── 04_toc_aware_chunking.ipynb
│   ├── 05_image_text_linking.ipynb
│   ├── 06_embedding_generation.ipynb
│   ├── 07_database_ingestion_and_indexing.ipynb
│   └── README.md
│
└── README.md
```

---

## Notebook Pipeline

The project is currently implemented as a sequential notebook pipeline.

| Step | Notebook                        | Purpose                                                                                    |
| ---- | ------------------------------- | ------------------------------------------------------------------------------------------ |
| 01   | Image Extraction and Filtering  | Extract images from the source PDF and remove noisy or irrelevant artifacts.               |
| 02   | PDF Structure Exploration       | Analyze the table of contents, headings, page structure, and document layout.              |
| 03   | Text Extraction and Cleaning    | Extract page-level text and clean repeated headers, footers, and formatting noise.         |
| 04   | TOC-Aware Chunking              | Create meaningful chunks based on document sections instead of blind fixed-size splitting. |
| 05   | Image-Text Linking              | Connect extracted images to related text chunks using page references and proximity.       |
| 06   | Embedding Generation            | Generate vector embeddings for text chunks using sentence-transformer models.              |
| 07   | Database Ingestion and Indexing | Store chunks, metadata, images, and embeddings inside PostgreSQL with pgvector.            |

---

## Technical Approach

### 1. Document Understanding

The pipeline starts by exploring the structure of the SCADA technical manual. Instead of treating the document as plain text, the project uses the table of contents and page-level metadata to preserve the logical structure of the manual.

This helps produce more accurate retrieval results because each chunk carries meaningful context such as section titles, page numbers, and hierarchy.

### 2. Semantic Chunking

The project uses TOC-aware chunking to split the manual into coherent technical sections. This is more suitable for engineering manuals than fixed-size chunking because technical information is often organized by procedures, components, and configuration topics.

### 3. Embedding Generation

Each text chunk is converted into a semantic vector representation. These embeddings allow the system to retrieve relevant manual sections based on meaning rather than exact keyword matching.

### 4. Vector Database Storage

PostgreSQL with pgvector is used as the retrieval backend. The database stores:

* Text chunks
* Chunk metadata
* Embedding vectors
* Extracted image references
* Links between chunks and related images

### 5. Future RAG Assistant

The final goal is to connect the retrieval layer to a language model so users can ask natural-language questions about the SCADA manual and receive grounded answers with citations.

---

## Example Use Cases

* Search SCADA manuals using natural language.
* Retrieve relevant troubleshooting sections.
* Find configuration steps quickly.
* Support engineers with cited technical answers.
* Link visual references to related text sections.
* Build a domain-specific industrial AI assistant.

---

## Technologies Used

* Python
* Jupyter Notebook
* PostgreSQL
* pgvector
* Sentence Transformers
* Semantic Search
* Vector Embeddings
* PDF Processing
* Retrieval-Augmented Generation
* Technical Document Processing

---

## Current Limitations

This repository is currently a research and prototyping version. The implementation is notebook-based and does not yet include a production backend, packaged modules, automated tests, or a deployed user interface.

The original technical manual, extracted data, images, embeddings, and generated intermediate files are not included in the repository because they may be private or copyrighted.

---

## Planned Improvements

* Refactor notebooks into a clean Python package.
* Add a modular `src/` structure.
* Add configuration files for paths, database settings, and model settings.
* Implement a FastAPI backend for retrieval and answer generation.
* Add a Streamlit or React-based user interface.
* Add logging, exception handling, and testing.
* Add Docker support for PostgreSQL and the application.
* Add evaluation scripts for retrieval quality.
* Add documentation for running the full pipeline locally.

---

## Project Status

This project is an early-stage AI engineering prototype. It demonstrates the core data processing and retrieval preparation pipeline required to build a domain-specific SCADA assistant.

The current version is intentionally notebook-based to support experimentation, validation, and future refactoring.

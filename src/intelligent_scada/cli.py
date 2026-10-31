"""Command-line interface for individual stages and the complete pipeline."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast

from intelligent_scada.artifacts import read_json
from intelligent_scada.chunking.toc_chunker import create_chunks
from intelligent_scada.config import Settings, document_key_from_name
from intelligent_scada.database.repository import DatabaseRepository
from intelligent_scada.logging_config import configure_logging
from intelligent_scada.pipeline import Pipeline
from intelligent_scada.rag.service import RAGService

LOGGER = logging.getLogger(__name__)


def _base_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="intelligent-scada",
        description="Build and query a retrieval-ready SCADA manual knowledge base.",
    )
    parser.add_argument("--data-dir", type=Path, help="Artifact directory (default: data)")
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING, or ERROR")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Run the complete PDF pipeline")
    ingest.add_argument("pdf", type=Path)
    ingest.add_argument("--document-name")
    ingest.add_argument("--document-key")
    ingest.add_argument("--resume", action="store_true")
    ingest.add_argument("--force", action="store_true")
    ingest.add_argument("--skip-images", action="store_true")
    ingest.add_argument("--skip-index", action="store_true")

    for command, help_text in (
        ("extract-images", "Extract and automatically filter PDF images"),
        ("analyze-pdf", "Analyze TOC and page structure"),
        ("extract-text", "Extract and clean page text"),
    ):
        stage = subparsers.add_parser(command, help=help_text)
        stage.add_argument("pdf", type=Path)
        stage.add_argument("--resume", action="store_true")
        stage.add_argument("--force", action="store_true")

    chunk = subparsers.add_parser("chunk", help="Build chunks from cleaned pages")
    chunk.add_argument("clean_pages", type=Path)
    chunk.add_argument("--structure", type=Path, required=True)
    chunk.add_argument("--output", type=Path)
    chunk.add_argument("--strategy", choices=("legacy", "targeted"))

    link = subparsers.add_parser("link-images", help="Link kept images to chunks")
    link.add_argument("--chunks", type=Path)
    link.add_argument("--manifest", type=Path)

    embed = subparsers.add_parser("embed", help="Generate normalized chunk embeddings")
    embed.add_argument("chunks", type=Path, nargs="?")

    init_db = subparsers.add_parser("init-db", help="Create database tables and indexes")
    init_db.add_argument("--schema", type=Path)

    index = subparsers.add_parser("index", help="Index previously generated artifacts")
    index.add_argument("pdf", type=Path)
    index.add_argument("--document-name")
    index.add_argument("--document-key")
    index.add_argument("--no-replace", action="store_true")

    ask = subparsers.add_parser("ask", help="Ask a grounded question")
    ask.add_argument("question")
    ask.add_argument("--document-key")
    ask.add_argument("--session-id")
    ask.add_argument("--no-memory", action="store_true")
    ask.add_argument("--images", action="store_true")
    ask.add_argument("--top-k", type=int)
    ask.add_argument("--json", action="store_true", dest="as_json")

    delete = subparsers.add_parser("delete-document", help="Delete one indexed manual")
    delete.add_argument("document_key")

    serve = subparsers.add_parser("serve", help="Start the FastAPI backend and web app")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    serve.add_argument("--reload", action="store_true")
    serve.add_argument("--workers", type=int)
    return parser


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env(data_dir=args.data_dir)
    document_name = getattr(args, "document_name", None) or settings.document_name
    requested_key = getattr(args, "document_key", None)
    document_key = requested_key or (
        document_key_from_name(document_name)
        if document_name != settings.document_name
        else settings.document_key
    )
    log_level = args.log_level.upper() if args.log_level else settings.log_level
    return replace(
        settings.for_document(
            document_name=document_name,
            document_key=document_key,
        ),
        log_level=log_level,
    )


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def run(args: argparse.Namespace) -> int:
    settings = _settings(args)
    configure_logging(settings.log_level)
    if args.command == "serve":
        import uvicorn

        settings = replace(settings, api_host=args.host or settings.api_host,
                           api_port=args.port if args.port is not None else settings.api_port,
                           api_workers=args.workers if args.workers is not None else settings.api_workers)
        settings.validate()
        settings.configure_worker_environment()
        uvicorn.run(
            "intelligent_scada.api.app:create_app",
            factory=True,
            host=args.host or settings.api_host,
            port=args.port or settings.api_port,
            reload=args.reload or settings.api_reload,
            workers=args.workers or settings.api_workers,
            log_level=settings.log_level.lower(),
        )
        return 0

    pipeline = Pipeline(settings)

    if args.command == "ingest":
        _print_json(
            pipeline.ingest(
                args.pdf.resolve(),
                resume=args.resume,
                force=args.force,
                include_images=not args.skip_images,
                include_index=not args.skip_index,
            )
        )
    elif args.command == "extract-images":
        extracted_images = pipeline.extract_images(
            args.pdf.resolve(), resume=args.resume, force=args.force
        )
        _print_json(
            {
                "images": len(extracted_images),
                "manifest": str(settings.filter_manifest_path),
            }
        )
    elif args.command == "analyze-pdf":
        structure = pipeline.analyze_pdf(
            args.pdf.resolve(), resume=args.resume, force=args.force
        )
        _print_json(
            {"pages": structure["total_pages"], "toc_entries": structure["toc_entries"]}
        )
    elif args.command == "extract-text":
        pages = pipeline.extract_text(args.pdf.resolve(), resume=args.resume, force=args.force)
        _print_json({"pages": len(pages), "output": str(settings.clean_text_path)})
    elif args.command == "chunk":
        structure = read_json(args.structure)
        clean_pages = read_json(args.clean_pages)
        output = args.output or settings.text_chunks_path
        strategy = cast(
            Literal["legacy", "targeted"],
            args.strategy or settings.chunking_strategy,
        )
        if output.resolve() == settings.text_chunks_path.resolve():
            pipeline = Pipeline(replace(settings, chunking_strategy=strategy))
            chunks = pipeline.chunk(structure, clean_pages)
        else:
            # Experimental exports are deliberately not signed for production indexing.
            chunks = create_chunks(
                structure, clean_pages, output, target=settings.chunk_target_size,
                maximum=settings.chunk_max_size, overlap=settings.chunk_overlap,
                strategy=strategy, skip_sections=settings.skip_sections,
            )
        _print_json({"chunks": len(chunks), "output": str(output)})
    elif args.command == "link-images":
        if args.chunks:
            settings.text_chunks_path.parent.mkdir(parents=True, exist_ok=True)
            chunks = read_json(args.chunks)
        else:
            chunks = None
        link_manifest = cast(Any, read_json(args.manifest)) if args.manifest else None
        links = pipeline.link_images(chunks, link_manifest)
        _print_json({"chunks": len(links), "output": str(settings.chunk_image_links_path)})
    elif args.command == "embed":
        chunks = read_json(args.chunks) if args.chunks else None
        pipeline.embed(chunks)
        _print_json({"embeddings": str(settings.embeddings_npy_path)})
    elif args.command == "init-db":
        schema = args.schema or settings.database_schema_path
        DatabaseRepository(settings.pg_conn_str).apply_schema(schema)
        _print_json({"schema": str(schema), "status": "applied"})
    elif args.command == "index":
        counts = pipeline.index(args.pdf.resolve(), replace=not args.no_replace)
        _print_json(counts)
    elif args.command == "ask":
        response = RAGService.from_settings(settings).ask(
            args.question,
            args.document_key or settings.document_key,
            session_id=args.session_id,
            memory_enabled=not args.no_memory,
            include_images=args.images or None,
            top_k=args.top_k,
        )
        if args.as_json:
            _print_json(response)
        else:
            print(response["answer"])
            if response["citations"]:
                print("\nSources:")
                for citation in response["citations"]:
                    print(f"[{citation['source_id']}] {citation['label']}")
            if response["related_images"]:
                print("\nRelated images:")
                for image in response["related_images"]:
                    print(f"- {image['filename']} (page {image['page']})")
    elif args.command == "delete-document":
        deleted = DatabaseRepository(settings.pg_conn_str).delete_document(args.document_key)
        _print_json({"document_key": args.document_key, "deleted": deleted})
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _base_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (FileNotFoundError, ValueError, RuntimeError, LookupError) as exc:
        configure_logging(getattr(args, "log_level", None) or "INFO")
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

"""LocalEmbeddingProvider — a concrete BaseEmbeddingProvider backed by
ChromaDB's own bundled default embedding function.

`chromadb` is already a project dependency (used by `ChromaKnowledgeRepository`
for storage) and its `DefaultEmbeddingFunction` runs a local ONNX
sentence-transformer model (`all-MiniLM-L6-v2`) entirely on-CPU — no new
external service, no API key, and (after the model's one-time local cache
download) no network dependency at request time. This is the "already-
approved dependency" this provider reuses rather than introducing a new
one (e.g. an OpenAI/Cohere embeddings API).

Deterministic: the same input text against the same cached model always
produces the same vector (no sampling/dropout at inference time).

The embedding function itself is injected (`embedding_function_factory`),
not imported eagerly at module scope — tests substitute a cheap fake
callable so no real model load or network access ever happens under
`pytest` (matching this milestone's "do not depend on live internet
access for automated tests" constraint). Production code (`app.bootstrap`)
simply omits the factory and gets the real ChromaDB default.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from app.providers.embedding.models import EmbeddingProviderConfig
from app.providers.embedding.provider import BaseEmbeddingProvider
from app.services.embedding.models import EmbeddingRequest

__all__ = ["LocalEmbeddingProvider", "DEFAULT_EMBEDDING_MODEL"]

DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

EmbeddingFunction = Callable[[list[str]], list[list[float]]]

_logger = logging.getLogger("marketmind.providers.embedding.local")


def _default_embedding_function() -> EmbeddingFunction:
    """Construct ChromaDB's bundled default embedding function.

    Imported lazily (inside the function, not at module scope) so this
    module never triggers a chromadb/onnxruntime import — let alone the
    model's one-time download — merely by being imported. Construction
    itself does not download anything; the model is fetched (and cached
    to disk) lazily, on the first actual call.
    """
    from chromadb.utils import embedding_functions

    return embedding_functions.DefaultEmbeddingFunction()  # type: ignore[return-value]


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """Generates embeddings via a local, CPU-only model — no external API call.

    `embed_one` never raises for a "the provider isn't configured" reason
    (there is no configuration beyond the model itself); it can still
    fail per the base class's normal retry path if the underlying model
    load or inference call raises (e.g. the on-disk cache is corrupt, or
    the one-time download failed for lack of network) — that failure is
    retried and, if still failing after `config.max_retries`, recorded as
    a `FailedEmbeddingRequest` by `BaseEmbeddingProvider.generate()`,
    never crashing the pipeline stage that called it.
    """

    def __init__(
        self,
        config: EmbeddingProviderConfig,
        embedding_function_factory: Callable[[], EmbeddingFunction] | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            config: Provider configuration (model name, retry policy).
            embedding_function_factory: Builds the callable `embed_one`
                delegates to. Defaults to ChromaDB's real
                `DefaultEmbeddingFunction`; tests inject a fake factory
                instead, so no real model is ever loaded under pytest.
                Called at most once — the constructed function is cached
                on first use (lazy, not at `__init__` time), so
                constructing this provider never itself touches disk,
                the network, or onnxruntime.
        """
        super().__init__(config)
        self._embedding_function_factory = embedding_function_factory or _default_embedding_function
        self._embedding_function: EmbeddingFunction | None = None
        # Guards first-time construction/warm-up (see `_get_embedding_function`)
        # against the concurrent-callers race described there. One provider
        # instance is shared across a whole ingestion batch, and
        # `BaseEmbeddingProvider.generate()` fires every request in a chunk
        # (up to `EmbeddingService.DEFAULT_MAX_BATCH_SIZE` = 100) concurrently
        # via `asyncio.gather` — without this lock, a cold provider sees all
        # of them race the lazy singleton check-then-set below.
        self._init_lock = asyncio.Lock()

    async def _get_embedding_function(self) -> EmbeddingFunction:
        """Return the shared embedding function, constructing and warming
        it exactly once even under concurrent callers.

        `DefaultEmbeddingFunction()`'s own construction does not download
        anything (per this module's docstring) — the ~80MB ONNX model is
        fetched lazily, on that function's *first actual call*. Before
        this lock existed, N concurrent `embed_one()` callers on a cold
        provider (real batches: up to 100, one whole ingestion chunk) each
        saw `self._embedding_function is None`, each constructed their own
        function object, and — worse — each could independently trigger
        that first-call download, multiple processes racing to write the
        same on-disk cache file. Observed live: a 130-article ingestion
        run against a freshly restarted container produced 95 embedding
        failures out of 130 (only the chunk-1 stragglers that raced badly;
        chunk 2, embedded after chunk 1's race had already corrupted or
        settled the cache, mostly succeeded) — exactly this bug, not a
        provider or model defect.

        Fixed with the standard check-lock-check-again pattern: the fast
        path (already warm) never touches the lock; the slow path
        (cold) has exactly one caller perform the real
        construction-and-warm-up while every other concurrent caller
        awaits the same lock and then reuses what that one caller built —
        never redoing it, never racing the download.
        """
        if self._embedding_function is not None:
            return self._embedding_function
        async with self._init_lock:
            if self._embedding_function is None:
                function = await asyncio.to_thread(self._embedding_function_factory)
                # Warm it now, still holding the lock: a real (if trivial)
                # call is what actually triggers the one-time on-disk
                # download for the real ChromaDB default — doing it here
                # means every other concurrent caller waiting on this lock
                # resumes against an already-fully-cached model, never
                # racing that download themselves.
                await asyncio.to_thread(function, ["marketmind embedding provider warmup"])
                self._embedding_function = function
        return self._embedding_function

    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        """Embed one request's text via the local model, off the event loop.

        The underlying embedding function is synchronous and CPU-bound
        (ONNX inference) — run via `asyncio.to_thread` so one embedding
        call never blocks the event loop other requests/connections share.
        """
        embedding_function = await self._get_embedding_function()
        vectors = await asyncio.to_thread(embedding_function, [request.text])
        return list(vectors[0])

    async def health_check(self) -> bool:
        """Report whether the embedding function is constructed and callable.

        Deliberately does not run a real embedding (which could trigger
        the one-time model download) — mirrors this codebase's existing
        convention (`ProviderHealth`'s own docstring) that a health check
        must never require a real, potentially-slow request to produce.
        Constructs the function directly here (bypassing `_get_embedding_function`'s
        own warm-up call) for exactly that reason — a health check must
        stay cheap and side-effect-free, never itself triggering the
        one-time download.
        """
        try:
            if self._embedding_function is not None:
                return True
            await asyncio.to_thread(self._embedding_function_factory)
        except Exception as exc:  # noqa: BLE001 - health check must never raise
            _logger.warning("local_embedding_provider_unhealthy", extra={"error": str(exc)})
            return False
        return True

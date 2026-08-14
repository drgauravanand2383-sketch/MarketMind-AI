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

    def _get_embedding_function(self) -> EmbeddingFunction:
        if self._embedding_function is None:
            self._embedding_function = self._embedding_function_factory()
        return self._embedding_function

    async def embed_one(self, request: EmbeddingRequest) -> list[float]:
        """Embed one request's text via the local model, off the event loop.

        The underlying embedding function is synchronous and CPU-bound
        (ONNX inference) — run via `asyncio.to_thread` so one embedding
        call never blocks the event loop other requests/connections share.
        """
        embedding_function = self._get_embedding_function()
        vectors = await asyncio.to_thread(embedding_function, [request.text])
        return list(vectors[0])

    async def health_check(self) -> bool:
        """Report whether the embedding function is constructed and callable.

        Deliberately does not run a real embedding (which could trigger
        the one-time model download) — mirrors this codebase's existing
        convention (`ProviderHealth`'s own docstring) that a health check
        must never require a real, potentially-slow request to produce.
        """
        try:
            self._get_embedding_function()
        except Exception as exc:  # noqa: BLE001 - health check must never raise
            _logger.warning("local_embedding_provider_unhealthy", extra={"error": str(exc)})
            return False
        return True

"""
Semantic keyword matcher using sentence-transformers (PyTorch-based).
Compares post text against keywords using cosine similarity.
"""

import logging
import numpy as np

logger = logging.getLogger(__name__)

_model = None
_model_name = None


def _get_model(model_name: str = 'all-MiniLM-L6-v2'):
    """Lazy-load the sentence transformer model (singleton)."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        logger.info(f"Loading semantic model: {model_name} ...")
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(model_name)
        _model_name = model_name
        logger.info("Semantic model loaded successfully")
    return _model


class SemanticMatcher:
    """
    Matches post text (title + description) against a set of keywords
    using semantic similarity powered by sentence-transformers.
    """

    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        self.model_name = model_name
        self._keyword_embeddings = None
        self._keywords = None

    def _ensure_model(self):
        return _get_model(self.model_name)

    def set_keywords(self, keywords: list[str]):
        """Pre-encode keywords for efficient repeated matching."""
        if not keywords:
            self._keywords = []
            self._keyword_embeddings = None
            return

        model = self._ensure_model()
        self._keywords = keywords
        self._keyword_embeddings = model.encode(keywords, convert_to_numpy=True,
                                                 normalize_embeddings=True)
        logger.info(f"Encoded {len(keywords)} keywords for matching")

    def match(self, post_title: str, post_description: str = '',
              threshold: float = 0.45) -> tuple[bool, float]:
        """
        Check if a post semantically matches the keywords.

        Args:
            post_title: Title of the post
            post_description: Description/body of the post
            threshold: Minimum similarity score to consider a match (0.0-1.0)

        Returns:
            Tuple of (is_match, best_similarity_score)
        """
        if self._keyword_embeddings is None or len(self._keywords) == 0:
            logger.warning("No keywords set for matching")
            return False, 0.0

        # Combine title and description for richer context
        post_text = post_title
        if post_description:
            post_text += " " + post_description[:500]

        model = self._ensure_model()
        post_embedding = model.encode([post_text], convert_to_numpy=True,
                                       normalize_embeddings=True)

        # Cosine similarity (embeddings are already normalized)
        similarities = np.dot(post_embedding, self._keyword_embeddings.T)[0]
        max_score = float(np.max(similarities))

        is_match = max_score >= threshold
        if is_match:
            best_keyword = self._keywords[int(np.argmax(similarities))]
            logger.debug(f"Match! score={max_score:.3f} keyword='{best_keyword}' "
                         f"title='{post_title[:60]}'")

        return is_match, max_score

    def batch_match(self, posts: list[dict], threshold: float = 0.45) -> list[dict]:
        """
        Match multiple posts at once (more efficient than one-by-one).

        Args:
            posts: List of dicts with 'title' and optionally 'description' keys
            threshold: Minimum similarity threshold

        Returns:
            List of posts enriched with 'is_match' and 'match_score' keys
        """
        if self._keyword_embeddings is None or len(self._keywords) == 0:
            for p in posts:
                p['is_match'] = False
                p['match_score'] = 0.0
            return posts

        texts = []
        for p in posts:
            t = p.get('title', '')
            d = p.get('description', '')[:500] if p.get('description') else ''
            texts.append(f"{t} {d}".strip())

        model = self._ensure_model()
        post_embeddings = model.encode(texts, convert_to_numpy=True,
                                        normalize_embeddings=True, batch_size=32)

        similarities = np.dot(post_embeddings, self._keyword_embeddings.T)
        max_scores = np.max(similarities, axis=1)

        for i, p in enumerate(posts):
            score = float(max_scores[i])
            p['is_match'] = score >= threshold
            p['match_score'] = score

        matched = sum(1 for p in posts if p['is_match'])
        logger.info(f"Batch match: {matched}/{len(posts)} posts matched (threshold={threshold})")
        return posts

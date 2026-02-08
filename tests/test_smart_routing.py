"""Test suite for Smart Routing features (filtering, embeddings, RAG search)."""

import os
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.dialects import postgresql

from src.registry.filtering import (
    extract_categories_from_prompt,
    should_include_tool,
    CATEGORY_KEYWORDS
)
from src.registry.embedding import generate_embedding, batch_generate_embeddings
from src.registry.repository import (
    get_tools_by_categories,
    get_core_tools,
    search_tools_by_embedding,
    increment_tool_usage
)
from src.registry.models import Tool, RiskLevel


def _embedding_model_cached() -> bool:
    model_name = "all-MiniLM-L6-v2"

    repo_cache = Path(__file__).resolve().parents[1] / "model_cache"
    if _has_model(repo_cache, model_name):
        return True

    st_home = os.getenv("SENTENCE_TRANSFORMERS_HOME")
    if st_home and _has_model(Path(st_home), model_name, check_sentence_transformers=True):
        return True

    hf_roots = [
        os.getenv("HF_HUB_CACHE"),
        os.getenv("TRANSFORMERS_CACHE"),
        os.getenv("HF_HOME"),
    ]
    for root in hf_roots:
        if not root:
            continue
        if _has_model(Path(root), model_name):
            return True

    default_hub = Path.home() / ".cache" / "huggingface" / "hub"
    return (default_hub / f"models--sentence-transformers--{model_name}").exists()


def _has_model(base_dir: Path, model_name: str, check_sentence_transformers: bool = False) -> bool:
    if not base_dir.exists():
        return False

    if check_sentence_transformers:
        for path in base_dir.rglob(f"*{model_name}*"):
            if path.is_dir():
                return True

    hub_path = base_dir if base_dir.name == "hub" else base_dir / "hub"
    model_dir = hub_path / f"models--sentence-transformers--{model_name}"
    return model_dir.exists()


class TestCategoryExtraction:
    """Tests for keyword-based category extraction."""
    
    def test_math_keywords(self):
        """Test extraction of math category keywords."""
        assert "math" in extract_categories_from_prompt("I need to calculate the sum")
        assert "math" in extract_categories_from_prompt("Convert 100 meters to feet")
        assert "math" in extract_categories_from_prompt("What's the average of these numbers?")
    
    def test_multiple_categories(self):
        """Test that multiple categories can be extracted."""
        categories = extract_categories_from_prompt("Read a file and calculate statistics")
        assert "filesystem" in categories
        assert "math" in categories
    
    def test_word_boundaries(self):
        """Test that partial matches are avoided with word boundaries."""
        # "add" is in "address" but shouldn't match
        categories = extract_categories_from_prompt("What's my address?")
        assert "math" not in categories
    
    def test_case_insensitive(self):
        """Test that matching is case-insensitive."""
        assert "math" in extract_categories_from_prompt("CALCULATE the AVERAGE")
        assert "math" in extract_categories_from_prompt("Calculate The Average")
    
    def test_empty_prompt(self):
        """Test that empty prompts return empty set."""
        assert extract_categories_from_prompt("") == set()
        assert extract_categories_from_prompt(None) == set()
    
    def test_no_matches(self):
        """Test prompts that don't match any categories."""
        categories = extract_categories_from_prompt("Hello, how are you?")
        assert len(categories) == 0


class TestToolFiltering:
    """Tests for tool inclusion logic."""
    
    def test_core_tools_always_included(self):
        """Core tools should always be included."""
        assert should_include_tool(["core"], set())
        assert should_include_tool(["core", "math"], set())
    
    def test_category_match_includes_tool(self):
        """Tools with matching categories should be included."""
        assert should_include_tool(["math"], {"math"})
        assert should_include_tool(["math", "filesystem"], {"filesystem"})
    
    def test_no_match_excludes_tool(self):
        """Tools without matching categories should be excluded."""
        assert not should_include_tool(["math"], {"filesystem"})
        assert not should_include_tool(["database"], {"web", "filesystem"})
    
    def test_empty_categories(self):
        """Tools with no categories and no matches should be excluded."""
        assert not should_include_tool([], set())
        assert not should_include_tool([], {"math"})


class TestEmbeddingGeneration:
    """Tests for embedding generation."""
    
    @pytest.mark.asyncio
    async def test_generate_embedding_shape(self):
        """Test that embeddings have correct dimensionality."""
        if not _embedding_model_cached():
            pytest.skip("Embedding model not cached locally (offline-safe skip).")
        try:
            embedding = await generate_embedding("Calculate the sum of two numbers")
            assert isinstance(embedding, list)
            assert len(embedding) == 384  # all-MiniLM-L6-v2 dimensions
            assert all(isinstance(x, float) for x in embedding)
        except RuntimeError as e:
            if "sentence-transformers not installed" in str(e):
                pytest.skip("sentence-transformers not installed")
            raise
    
    @pytest.mark.asyncio
    async def test_batch_embeddings(self):
        """Test batch embedding generation."""
        if not _embedding_model_cached():
            pytest.skip("Embedding model not cached locally (offline-safe skip).")
        try:
            texts = [
                "Calculate the sum",
                "Read a file",
                "Query the database"
            ]
            embeddings = await batch_generate_embeddings(texts)
            assert len(embeddings) == 3
            assert all(len(emb) == 384 for emb in embeddings)
        except RuntimeError as e:
            if "sentence-transformers not installed" in str(e):
                pytest.skip("sentence-transformers not installed")
            raise
    
    @pytest.mark.asyncio
    async def test_similar_texts_have_similar_embeddings(self):
        """Test that semantically similar texts produce similar embeddings."""
        if not _embedding_model_cached():
            pytest.skip("Embedding model not cached locally (offline-safe skip).")
        try:
            emb1 = await generate_embedding("Calculate the sum of two numbers")
            emb2 = await generate_embedding("Add two numbers together")
            emb3 = await generate_embedding("Read file contents from disk")
            
            # Compute cosine similarity
            def cosine_similarity(a, b):
                import math
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x * x for x in a))
                norm_b = math.sqrt(sum(y * y for y in b))
                return dot / (norm_a * norm_b)
            
            sim_12 = cosine_similarity(emb1, emb2)
            sim_13 = cosine_similarity(emb1, emb3)
            
            # Math-related texts should be more similar to each other
            assert sim_12 > sim_13
        except RuntimeError as e:
            if "sentence-transformers not installed" in str(e):
                pytest.skip("sentence-transformers not installed")
            raise


class TestRepositoryFunctions:
    """Tests for repository layer smart routing functions."""
    
    @pytest.mark.asyncio
    async def test_get_tools_by_categories(self):
        """Test category-based tool retrieval."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            Tool(id=1, name="calc", description="Calculator", backend_url="http://x",
                 risk_level=RiskLevel.low, is_active=True, categories=["math"])
        ]
        db.execute.return_value = mock_result
        
        tools = await get_tools_by_categories(db, ["math"])
        assert len(tools) == 1
        assert tools[0].name == "calc"

        stmt = db.execute.call_args.args[0]
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "VARCHAR(50)[]" in compiled
        assert "TEXT[]" not in compiled
    
    @pytest.mark.asyncio
    async def test_get_core_tools(self):
        """Test core tool retrieval."""
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            Tool(id=1, name="help", description="Help", backend_url="http://x",
                 risk_level=RiskLevel.low, is_active=True, categories=["core"])
        ]
        db.execute.return_value = mock_result
        
        tools = await get_core_tools(db)
        assert len(tools) == 1
        assert "core" in tools[0].categories

        stmt = db.execute.call_args.args[0]
        compiled = str(stmt.compile(dialect=postgresql.dialect()))
        assert "VARCHAR(50)[]" in compiled
        assert "TEXT[]" not in compiled
    
    @pytest.mark.asyncio
    async def test_increment_tool_usage(self):
        """Test usage counter increment."""
        db = AsyncMock()
        
        await increment_tool_usage(db, tool_id=5)
        
        # Verify execute was called
        assert db.execute.called
        # Verify commit was called
        assert db.commit.called


class TestSmartRoutingIntegration:
    """Integration tests for the complete smart routing pipeline."""
    
    @pytest.mark.asyncio
    async def test_math_prompt_returns_math_tools(self):
        """Test that math-related prompts filter for math tools."""
        # Extract categories from prompt
        categories = extract_categories_from_prompt("Calculate the average of 10 and 20")
        assert "math" in categories
        
        # Check that math tool would be included
        assert should_include_tool(["math"], categories)
        
        # Check that non-math tool would be excluded
        assert not should_include_tool(["filesystem"], categories)
    
    @pytest.mark.asyncio
    async def test_core_tools_always_returned(self):
        """Test that core tools are returned regardless of prompt."""
        # Empty prompt
        categories = extract_categories_from_prompt("")
        assert should_include_tool(["core"], categories)
        
        # Math prompt
        categories = extract_categories_from_prompt("Calculate sum")
        assert should_include_tool(["core"], categories)
        
        # Filesystem prompt
        categories = extract_categories_from_prompt("Read file")
        assert should_include_tool(["core"], categories)

"""Scelta del client LLM da variabili d'ambiente (nessuna chiamata al modello)."""

from __future__ import annotations

import os
import unittest
from unittest import mock

from datapizza.clients.openai_like import OpenAILikeClient

from breakfix.agent import MAX_OUTPUT_TOKENS, OLLAMA_BASE_URL, build_llm_client, generation_kwargs


def llm_env(**values: str) -> mock._patch_dict:
    """Ambiente con solo le variabili LLM indicate (senza svuotare quelle di sistema: servono a SSL)."""
    env = {key: value for key, value in os.environ.items() if not key.startswith(("LLM_", "OLLAMA_"))}
    return mock.patch.dict(os.environ, {**env, **values}, clear=True)


class OllamaClientTest(unittest.TestCase):
    def test_ollama_needs_no_api_key(self) -> None:
        with llm_env(LLM_PROVIDER="ollama"):
            client = build_llm_client()

        self.assertIsInstance(client, OpenAILikeClient)
        self.assertEqual(client.model_name, "breakfix-qwen3")
        self.assertEqual(client.base_url, OLLAMA_BASE_URL)

    def test_model_and_url_can_be_overridden(self) -> None:
        with llm_env(LLM_PROVIDER="ollama", LLM_MODEL="qwen3:8b", OLLAMA_BASE_URL="http://ollama:11434/v1"):
            client = build_llm_client()

        self.assertEqual(client.model_name, "qwen3:8b")
        self.assertEqual(client.base_url, "http://ollama:11434/v1")


class GenerationKwargsTest(unittest.TestCase):
    def test_reasoning_effort_only_when_set(self) -> None:
        with llm_env():
            self.assertEqual(generation_kwargs(), {"max_tokens": MAX_OUTPUT_TOKENS})
        with llm_env(LLM_REASONING_EFFORT="none"):
            self.assertEqual(generation_kwargs()["reasoning_effort"], "none")


if __name__ == "__main__":
    unittest.main()

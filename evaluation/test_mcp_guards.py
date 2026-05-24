"""Unit tests for the Subtask F MCP guards (SSRF + path-traversal).

Stdlib-only. Runs without Docker, Qdrant, Neo4j, or any LLM.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from core.mcp.path_guard import (  # noqa: E402
    PathGuardError,
    validate_local_path,
    validate_object_name,
)
from core.mcp.url_guard import SSRFGuardError, validate_url  # noqa: E402


class TestObjectName(unittest.TestCase):
    def test_accepts_simple_key(self):
        self.assertEqual(validate_object_name("tunisia/code.pdf"), "tunisia/code.pdf")

    def test_accepts_single_segment(self):
        self.assertEqual(validate_object_name("file.pdf"), "file.pdf")

    def test_rejects_absolute(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("/etc/passwd")

    def test_rejects_traversal(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("../../../etc/passwd")

    def test_rejects_nested_traversal(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("tunisia/../../etc/passwd")

    def test_rejects_backslash(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("tunisia\\code.pdf")

    def test_rejects_null_byte(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("tunisia/code.pdf\x00.txt")

    def test_rejects_double_slash(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("tunisia//code.pdf")

    def test_rejects_empty(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("")

    def test_rejects_overly_long(self):
        with self.assertRaises(PathGuardError):
            validate_object_name("a" * 600)


class TestLocalPath(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="path_guard_test_")

    def test_accepts_inside_root(self):
        target = os.path.join(self.root, "foo.pdf")
        self.assertEqual(validate_local_path(target, allowed_root=self.root), target)

    def test_rejects_outside_root(self):
        with self.assertRaises(PathGuardError):
            validate_local_path("/etc/passwd", allowed_root=self.root)

    def test_rejects_traversal_resolving_outside(self):
        target = os.path.join(self.root, "..", "outside.pdf")
        with self.assertRaises(PathGuardError):
            validate_local_path(target, allowed_root=self.root)

    def test_rejects_null_byte(self):
        with self.assertRaises(PathGuardError):
            validate_local_path("/tmp/foo\x00.pdf", allowed_root=self.root)


class TestUrlGuard(unittest.TestCase):
    def test_accepts_ollama_cloud_https(self):
        url = "https://ollama.com/api/generate"
        self.assertEqual(validate_url(url, context="t"), url)

    def test_accepts_huggingface_https(self):
        url = "https://huggingface.co/BAAI/bge-m3"
        self.assertEqual(validate_url(url, context="t"), url)

    def test_accepts_local_qdrant_http(self):
        url = "http://localhost:6333/collections"
        self.assertEqual(validate_url(url, context="t"), url)

    def test_rejects_http_external(self):
        with self.assertRaises(SSRFGuardError):
            validate_url("http://ollama.com/api/generate", context="t")

    def test_rejects_metadata_imds(self):
        with self.assertRaises(SSRFGuardError):
            validate_url("https://169.254.169.254/latest/meta-data/", context="t")

    def test_rejects_private_ip_literal(self):
        with self.assertRaises(SSRFGuardError):
            validate_url("https://10.0.0.5/", context="t")

    def test_rejects_unknown_external_host(self):
        with self.assertRaises(SSRFGuardError):
            validate_url("https://attacker.example.com/", context="t")

    def test_rejects_missing_scheme(self):
        with self.assertRaises(SSRFGuardError):
            validate_url("ollama.com/api/generate", context="t")

    def test_rejects_empty(self):
        with self.assertRaises(SSRFGuardError):
            validate_url("", context="t")

    def test_accepts_explicit_per_call_allowlist(self):
        # example.com is IANA-reserved but resolves to a real public IP.
        url = "https://example.com/foo"
        self.assertEqual(
            validate_url(url, context="t", allowlist=["example.com"]),
            url,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

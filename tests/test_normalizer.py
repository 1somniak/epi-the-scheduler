"""Unit tests for name normalization and identity resolution."""

import unittest

from scheduler.normalizer import AmbiguousNameError, IdentityResolver, NameMatcher


class TestNameMatcher(unittest.TestCase):
    def test_agents_md_louis_rodet_examples(self):
        """Tests all variations from AGENTS.md Section 3 for Louis Rodet."""
        matcher = NameMatcher("louis", ["rodet"])

        examples = [
            "Louis Rodet",
            "louis rodet",
            "Louis",
            "louis.r",
            "louis.r.",
            "louis r",
            "L. Rodet",
            "louisr",
        ]
        for query in examples:
            with self.subTest(query=query):
                self.assertTrue(matcher.matches(query), f"Failed to match: {query}")

    def test_accent_and_hyphen_normalization(self):
        matcher = NameMatcher("avril", ["entat", "pantagene"])
        self.assertTrue(matcher.matches("Avril Entat-pantagène"))
        self.assertTrue(matcher.matches("avril"))
        self.assertTrue(matcher.matches("Avril E"))
        self.assertTrue(matcher.matches("avril.entat-pantagène"))

    def test_distinct_names_do_not_match(self):
        matcher = NameMatcher("thibault", ["daguier"])
        self.assertFalse(matcher.matches("Thibaud G"))
        self.assertFalse(matcher.matches("Thibaud"))
        self.assertFalse(matcher.matches("Antoine"))


class TestIdentityResolver(unittest.TestCase):
    def test_ambiguity_detection(self):
        """Verify that multiple people with same first name raise AmbiguousNameError on first-name-only query."""
        resolver = IdentityResolver()
        p1 = resolver.register_person("Louis Rodet", is_board=True)
        p2 = resolver.register_person("Louis Dupont", is_board=False)

        # Ambiguous query
        with self.assertRaises(AmbiguousNameError) as ctx:
            resolver.resolve("Louis")
        self.assertIn("Louis Rodet", str(ctx.exception))
        self.assertIn("Louis Dupont", str(ctx.exception))

        # Disambiguated queries
        self.assertEqual(resolver.resolve("Louis R"), p1)
        self.assertEqual(resolver.resolve("Louis D"), p2)
        self.assertEqual(resolver.resolve("Louis Dupont"), p2)


if __name__ == "__main__":
    unittest.main()

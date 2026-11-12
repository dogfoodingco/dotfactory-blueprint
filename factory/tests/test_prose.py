"""Prose patterns: fixtures, house style and code masking."""
import unittest

from dotfactory import prose


def ids(text):
    return [item.pattern for item in prose.scan(text)]


class ProseTests(unittest.TestCase):
    def test_fail_fixture(self):
        found = ids("This plan serves as a pivotal foundation that seamlessly leverages...")
        self.assertEqual(["copula-avoidance", "ai-vocabulary", "ai-vocabulary", "ai-vocabulary"], found)

    def test_pass_fixtures_and_house_style(self):
        for text in (
            "`.gitignore`: `.claude/` and `/build/`.",
            "An empty selection is a finding, not a pass.",
            "A rule whose subject is unreachable is skipped out loud, never silently passed.",
            "Name by goal, not mechanism.",
            "This is renderer code, so the order is enforced by tests, not by prompts.",
        ):
            self.assertEqual([], ids(text), text)

    def test_each_pattern(self):
        cases = {
            "ai-vocabulary": ["We delve into it.", "a tapestry of", "Underscoring the risk",
                              "It is a testament to", "Seamless handoff"],
            "copula-avoidance": ["The ledger serves as the record.", "It stands as proof.",
                                 "This acts as an index.", "The checks serve as lint."],
            "chatbot-frame": ["Great question!", "I hope this helps.", "Let me know if you want more."],
            "generic-close": ["In summary, it works.", "Overall, fine.", "  - In conclusion the run passed."],
            "negative-parallelism": ["It is not just a check, but a gate.",
                                     "not only the plan but also the demo"],
        }
        for pattern, texts in cases.items():
            for text in texts:
                self.assertEqual([pattern], ids(text), text)

    def test_near_misses_stay_clean(self):
        for text in (
            "Overall the run passed.",          # no comma: not the generic close
            "The summary, overall, is short.",  # not at line start
            "not just yet",                     # no contrastive clause
            "Not only that.",                   # no 'but also'
            "It was not just X. But later Y.",  # crosses a sentence
            "the deliverable plan",             # 'delve' substring only
            "acts as expected",                 # 'acts as a' requires the article
        ):
            self.assertEqual([], ids(text), text)

    def test_code_is_masked_and_offsets_survive(self):
        text = "Set `leverage_ratio`.\n```\nserves as\n```\nThen delve."
        found = prose.scan(text)
        self.assertEqual(["ai-vocabulary"], [item.pattern for item in found])
        self.assertEqual("delve", text[found[0].start:found[0].end])

    def test_quoted_mentions_are_masked(self):
        self.assertEqual([], ids('| Copula avoidance | "serves as", "stands as" |'))
        self.assertEqual([], ids("The list bans only \u201cnot just X, but Y\u201d."))
        self.assertEqual(["ai-vocabulary"], ids('He said "ok" and then delved.'))
        long_quote = '"' + "x " * 50 + 'delve"'
        self.assertEqual(["ai-vocabulary"], ids(long_quote))

    def test_enumerated_vocabulary_is_a_mention(self):
        for text in (
            "| AI vocabulary | delve, pivotal, seamless(ly), leverage(s), tapestry, testament, underscore(s) |",
            "Avoid delve, pivotal, and seamless.",
            "delve/pivotal/seamless",
        ):
            self.assertEqual([], ids(text), text)
        # Prose that uses the words is not an enumeration, even with commas between some of them.
        self.assertEqual(["ai-vocabulary"] * 4, ids("We delve into the pivotal, seamless tapestry of features."))
        self.assertEqual(["ai-vocabulary"] * 3, ids("This seamless change is pivotal, and we delve deeper."))
        self.assertEqual(["ai-vocabulary"] * 2, ids("Avoid delve and pivotal."))  # two words are not a list

    def test_empty_and_subset(self):
        self.assertEqual([], prose.scan(""))
        self.assertEqual([], ids(""))
        self.assertEqual([], prose.scan("delve", patterns=("chatbot-frame",)))

    def test_warnings_carry_source_line_and_cap(self):
        result = prose.warnings({"plan.md": "ok\nWe delve.", "delivery.json summary": "fine"})
        self.assertEqual([{"pattern": "ai-vocabulary", "source": "plan.md", "line": 2, "text": "delve"}], result)
        self.assertEqual(prose.MAX_WARNINGS, len(prose.warnings({"x": "delve " * 50})))

    def test_pattern_ids_are_unique(self):
        self.assertEqual(len(prose.PATTERN_IDS), len(set(prose.PATTERN_IDS)))


if __name__ == "__main__":
    unittest.main()

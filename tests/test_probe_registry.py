from __future__ import annotations

import dataclasses
import re
import unittest

from macr_runtime.canonical import sha256_id
from macr_runtime.probe_registry import (
    ProbeClass,
    ProbeDefinition,
    ProbeRegistry,
)


SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROLE = sha256_id("role_definition_v1", {"role": "worker"})
VERIFIER = sha256_id("verifier_suite_v1", {"version": "1"})
TASK_PACK = sha256_id("task_pack_v1", {"pack": "exact-output"})


def probe() -> ProbeDefinition:
    return ProbeDefinition.create(
        "p0-exact-worker-v1",
        ProbeClass.P0_EXACT_OUTPUT,
        "1.0.0",
        role_digest=ROLE,
        context_class="public_text",
        verifier_suite_digest=VERIFIER,
        task_pack_digest=TASK_PACK,
        held_out_variant_count=8,
        cost_ceiling_usd=0.05,
        mutation_controls=("trailing_newline", "markdown_fence"),
        contamination_notes_digest="a" * 64,
    )


class ProbeRegistryTests(unittest.TestCase):
    def test_probe_digest_is_stable_canonical_and_covers_verifier_role_controls(self) -> None:
        definition = probe()
        reordered = ProbeDefinition.create(
            "p0-exact-worker-v1",
            ProbeClass.P0_EXACT_OUTPUT,
            "1.0.0",
            role_digest=ROLE,
            context_class="public_text",
            verifier_suite_digest=VERIFIER,
            task_pack_digest=TASK_PACK,
            held_out_variant_count=8,
            cost_ceiling_usd=0.05,
            mutation_controls=("markdown_fence", "trailing_newline"),
            contamination_notes_digest="a" * 64,
        )

        self.assertRegex(definition.probe_digest, SHA256)
        self.assertEqual(definition, reordered)
        self.assertNotEqual(
            definition.probe_digest,
            dataclasses.replace(
                definition,
                verifier_suite_digest="b" * 64,
                probe_digest=ProbeDefinition.create(
                    definition.probe_id,
                    definition.probe_class,
                    definition.version,
                    role_digest=definition.role_digest,
                    context_class=definition.context_class,
                    verifier_suite_digest="b" * 64,
                    task_pack_digest=definition.task_pack_digest,
                    held_out_variant_count=definition.held_out_variant_count,
                    cost_ceiling_usd=definition.cost_ceiling_usd,
                    mutation_controls=definition.mutation_controls,
                    contamination_notes_digest=(
                        definition.contamination_notes_digest
                    ),
                ).probe_digest,
            ).probe_digest,
        )

    def test_registry_is_exact_and_rejects_digest_collision_or_unknown(self) -> None:
        definition = probe()
        registry = ProbeRegistry((definition,))

        self.assertEqual(registry.get(definition.probe_digest), definition)
        with self.assertRaisesRegex(KeyError, "unknown probe"):
            registry.get("f" * 64)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            ProbeRegistry((definition, definition))

    def test_probe_contract_rejects_unversioned_or_unbounded_definitions(self) -> None:
        with self.assertRaisesRegex(ValueError, "version"):
            ProbeDefinition.create(
                "bad",
                ProbeClass.P0_EXACT_OUTPUT,
                "",
                role_digest=ROLE,
                context_class="public_text",
                verifier_suite_digest=VERIFIER,
                task_pack_digest=TASK_PACK,
                held_out_variant_count=1,
                cost_ceiling_usd=0,
            )
        with self.assertRaisesRegex(ValueError, "held_out_variant_count"):
            ProbeDefinition.create(
                "bad",
                ProbeClass.P0_EXACT_OUTPUT,
                "1",
                role_digest=ROLE,
                context_class="public_text",
                verifier_suite_digest=VERIFIER,
                task_pack_digest=TASK_PACK,
                held_out_variant_count=0,
                cost_ceiling_usd=0,
            )


if __name__ == "__main__":
    unittest.main()

import os
import sys
import unittest
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.ai.providers.base_provider import AIProvider
from backend.ai.providers.ollama_provider import OllamaProvider
from backend.ai.providers.api_provider import APIProvider
from backend.ai.providers.provider_manager import get_provider_manager, encrypt_secret, decrypt_secret
from backend.ai.nlu.intent_parser import (
    IntentParser,
    INTENT_LIST_SOURCE_TABLES,
    INTENT_ANALYZE_NULL_VALUES,
    INTENT_BUILD_TARGET,
    INTENT_RECONCILIATION_LOGIC,
    INTENT_CHECK_CONTROL,
    INTENT_EXPLAIN_FAILURE,
    INTENT_MAKE_GENERIC,
    INTENT_SUMMARIZE_PROJECT,
)
from backend.ai.nlu.entity_extractor import EntityExtractor
from backend.ai.context.hla_context import HLAContextExtractor
from backend.ai.tools.hla_tools import HLAToolRegistry
from backend.ai.tools.validation_tools import ValidationTools


class TestAIProviderArchitecture(unittest.TestCase):

    def test_ollama_provider_implements_interface(self):
        ollama = OllamaProvider(base_url="http://127.0.0.1:11434", model="qwen3:latest")
        self.assertIsInstance(ollama, AIProvider)
        self.assertEqual(ollama.get_model(), "qwen3:latest")
        self.assertFalse(ollama.is_cloud())
        self.assertTrue(hasattr(ollama, "chat"))
        self.assertTrue(hasattr(ollama, "generate"))
        self.assertTrue(hasattr(ollama, "health_check"))
        self.assertTrue(hasattr(ollama, "is_available"))

    def test_api_provider_implements_interface(self):
        api_p = APIProvider(provider_type="openai", api_key="sk-testkey1234567890", model="gpt-4o-mini")
        self.assertIsInstance(api_p, AIProvider)
        self.assertEqual(api_p.get_model(), "gpt-4o-mini")
        self.assertTrue(api_p.is_cloud())
        self.assertTrue(api_p.is_available())
        self.assertEqual(api_p.get_masked_api_key(), "sk-••••7890")

    def test_standard_response_structure(self):
        ollama = OllamaProvider(model="qwen3:latest")
        resp = ollama.format_standard_response(
            text="Test output",
            intent=INTENT_LIST_SOURCE_TABLES,
            entities={"control_number": "23"},
            confidence=0.95
        )
        self.assertEqual(resp["text"], "Test output")
        self.assertEqual(resp["intent"], INTENT_LIST_SOURCE_TABLES)
        self.assertEqual(resp["entities"], {"control_number": "23"})
        self.assertEqual(resp["provider"], "ollama")
        self.assertEqual(resp["model"], "qwen3:latest")
        self.assertEqual(resp["confidence"], 0.95)

    def test_default_provider_is_ollama(self):
        mgr = get_provider_manager()
        mgr.switch_provider("ollama")
        self.assertEqual(mgr.active_provider_type, "ollama")
        self.assertIsInstance(mgr.get_active_provider(), OllamaProvider)
        self.assertFalse(mgr.get_active_provider().is_cloud())

    def test_switch_to_api_provider(self):
        mgr = get_provider_manager()
        mgr.switch_provider("api")
        self.assertEqual(mgr.active_provider_type, "api")
        self.assertIsInstance(mgr.get_active_provider(), APIProvider)
        self.assertTrue(mgr.get_active_provider().is_cloud())

        # Switch back to default
        mgr.switch_provider("ollama")
        self.assertEqual(mgr.active_provider_type, "ollama")

    def test_secret_encryption_and_decryption(self):
        raw_key = "sk-proj-mySuperSecretApiKey123456"
        encrypted = encrypt_secret(raw_key)
        self.assertNotEqual(encrypted, raw_key)
        self.assertNotIn("mySuperSecretApiKey", encrypted)
        decrypted = decrypt_secret(encrypted)
        self.assertEqual(decrypted, raw_key)

    def test_status_never_exposes_raw_api_key(self):
        mgr = get_provider_manager()
        mgr.configure_api(api_key="sk-live-secret-test-key-999999999")
        status = mgr.get_status()
        status_json = json.dumps(status)
        self.assertNotIn("secret-test-key", status_json)
        self.assertTrue(status["api"]["masked_key"].startswith("sk-"))
        self.assertIn("••••", status["api"]["masked_key"])

    def test_no_silent_fallback_when_ollama_offline(self):
        ollama = OllamaProvider(base_url="http://127.0.0.1:9999", model="qwen3:latest")
        health = ollama.health_check()
        self.assertFalse(health["available"])
        self.assertIn("Local Ollama is unavailable", health["error"])

    def test_generic_document_without_control_number(self):
        doc_analysis = {
            "overview": {
                "title": "Universal Payment Reconciliation Pipeline",
                "description": "Daily payment gateway reconciliation",
                "schedule": "Hourly"
            },
            "input_datasets": [
                {"name": "stripe_charges", "schema": "raw_payments", "description": "Raw API charge events"},
                {"name": "bank_settlements", "schema": "settlements", "description": "Settled ACH batch files"}
            ],
            "transformations": [
                {"id": "TR-01", "name": "Filter Successful Charges", "description": "Keep status = 'succeeded'"},
                {"id": "TR-02", "name": "Match Amounts", "description": "Variance calculation between stripe and bank"}
            ],
            "target_attributes": [
                {"name": "reconciliation_key", "type": "VARCHAR(64)"},
                {"name": "variance_amount", "type": "NUMERIC(18,2)"}
            ]
        }

        indexed = HLAContextExtractor.index_document_analysis(doc_analysis)
        self.assertEqual(indexed["document_profile"]["title"], "Universal Payment Reconciliation Pipeline")
        self.assertEqual(len(indexed["source_tables"]), 2)
        self.assertEqual(indexed["source_tables"][0]["name"], "stripe_charges")
        self.assertEqual(len(indexed["rules"]), 2)
        self.assertEqual(indexed["rules"][0]["id"], "TR-01")
        self.assertEqual(len(indexed["target_attributes"]), 2)

    def test_intent_parsing_varied_queries(self):
        test_cases = [
            ("show me the source tables for control 23", INTENT_LIST_SOURCE_TABLES),
            ("what source tables are used?", INTENT_LIST_SOURCE_TABLES),
            ("why is this null?", INTENT_ANALYZE_NULL_VALUES),
            ("why is circuit_id null?", INTENT_ANALYZE_NULL_VALUES),
            ("build the target", INTENT_BUILD_TARGET),
            ("generate target schema", INTENT_BUILD_TARGET),
            ("show me the reconciliation logic", INTENT_RECONCILIATION_LOGIC),
            ("explain R11 balance rules", INTENT_RECONCILIATION_LOGIC),
            ("check control 23", INTENT_CHECK_CONTROL),
            ("why did this fail?", INTENT_EXPLAIN_FAILURE),
            ("make this generic", INTENT_MAKE_GENERIC),
            ("don't copy source directly to target", INTENT_MAKE_GENERIC),
            ("summarize this project's controls", INTENT_SUMMARIZE_PROJECT),
        ]
        for query, expected_intent in test_cases:
            intent, conf = IntentParser.parse_intent(query)
            self.assertEqual(intent, expected_intent, f"Failed for query: '{query}'")
            self.assertGreater(conf, 0.8)

    def test_entity_extraction(self):
        e1 = EntityExtractor.extract_entities("show me the source tables for control 23")
        self.assertEqual(e1.get("control_number"), "23")

        e2 = EntityExtractor.extract_entities("check CTRL-104 in dev")
        self.assertEqual(e2.get("control_number"), "104")
        self.assertEqual(e2.get("environment"), "dev")

        e3 = EntityExtractor.extract_entities("why is circuit_id null?")
        self.assertEqual(e3.get("column"), "circuit_id")

        e4 = EntityExtractor.extract_entities("explain rule R11 reconciliation logic")
        self.assertEqual(e4.get("rule_id"), "R11")

    def test_sql_safety_validation(self):
        unsafe_sql = "DROP TABLE target_recon; DELETE FROM audit_log;"
        res_unsafe = ValidationTools.validate_sql_safety(unsafe_sql)
        self.assertFalse(res_unsafe["safe"])

        safe_sql = "CREATE TABLE IF NOT EXISTS target_dev.generic_recon (_recon_id VARCHAR(64));"
        res_safe = ValidationTools.validate_sql_safety(safe_sql)
        self.assertTrue(res_safe["safe"])

    def test_generic_target_principles(self):
        principles = HLAToolRegistry.explain_generic_target_principles()
        self.assertIn("Do NOT copy source tables directly", principles["principle"])
        self.assertGreaterEqual(len(principles["rules"]), 4)


if __name__ == "__main__":
    unittest.main()

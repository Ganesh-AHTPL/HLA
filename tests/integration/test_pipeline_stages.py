"""
Integration tests for 8-Stage pipeline planning, preview, and deployment.
"""

import unittest
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import create_engine
from backend.core.control_context import ControlContext
from backend.hla.hla_model import HLAControl, HLASourceStreamDef, HLAAttributeDef
from backend.hla.entity_parser import EntityParser
from backend.deployment.deployment_engine import DeploymentEngine
from config import Config


class TestPipelineDeploymentIntegration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(Config.SQLALCHEMY_DATABASE_URI)
        from sqlalchemy import text
        with cls.engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS reports"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS cmdb"))
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS ra_ctrl"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS reports.dl_vdom_firewall_audit_report (application_name VARCHAR(255))"))
            conn.execute(text("CREATE TABLE IF NOT EXISTS cmdb.dl_itsm_cmdb_daily_dump (production_ip VARCHAR(255), cmdb_production_ip VARCHAR(255))"))
            try:
                conn.execute(text("ALTER TABLE cmdb.dl_itsm_cmdb_daily_dump ADD COLUMN IF NOT EXISTS production_ip VARCHAR(255)"))
            except Exception:
                pass

        cls.deployment_engine = DeploymentEngine(cls.engine)
        cls.deployment_engine.planner.dep_resolver.source_resolver.registry.register_stream(
            "VUTM/DOOS", "reports", "dl_vdom_firewall_audit_report", "Reports DB", "SRC001"
        )
        cls.deployment_engine.planner.dep_resolver.source_resolver.registry.register_stream(
            "CMDB", "cmdb", "dl_itsm_cmdb_daily_dump", "ITSM DB", "SRC002"
        )

    def test_end_to_end_preview_and_dry_run(self):
        context = ControlContext(
            control_id=88,
            control_name="Integration Multi-Stage Control",
            target_schema="ra_ctrl"
        )

        hla = HLAControl(
            control_id=88,
            control_name="Integration Multi-Stage Control",
            source_streams={
                "VUTM/DOOS": HLASourceStreamDef(stream_name="VUTM/DOOS", source_system="Firewall"),
                "CMDB": HLASourceStreamDef(stream_name="CMDB", source_system="ITSM")
            },
            attributes=[
                HLAAttributeDef(attribute_name="Application_Name", source_stream="VUTM/DOOS", target_field_name="application_name"),
                HLAAttributeDef(attribute_name="CMDB_Production_IP", source_stream="CMDB", target_field_name="cmdb_production_ip")
            ]
        )
        hla.entities = EntityParser.plan_entities_for_control(hla)

        # 1. Test Preview
        preview = self.deployment_engine.preview_deployment(hla, context)
        self.assertTrue(preview["success"])
        self.assertTrue(preview["can_deploy"])
        self.assertGreater(len(preview["entities"]), 0)

        # 2. Test Dry Run Deployment
        res = self.deployment_engine.execute_deployment(hla, context, dry_run=True)
        self.assertTrue(res.success)
        self.assertIn("Dry run", res.warnings[0])


if __name__ == "__main__":
    unittest.main()

import json
from pathlib import Path
import tempfile
import unittest
from source_versions import versions


class VersionTests(unittest.TestCase):
    def test_real_contract_exports_six_immutable_pins(self):
        pins = versions(Path(__file__).resolve().parents[1])
        self.assertEqual(len(pins), 6)
        self.assertEqual(pins['three_arm_code'], '8534d90f801abff8ace07938f9cc104feeaac407')

    def test_missing_or_mutable_pin_rejected(self):
        original = json.loads((Path(__file__).resolve().parents[1] / 'config/source-contract.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            for bad in ('main', 'abc', '123\nother=value'):
                original['workflow_pins']['code'] = bad
                (root / 'config/source-contract.json').write_text(json.dumps(original))
                with self.assertRaises(ValueError):
                    versions(root)
            original['workflow_pins'].pop('code')
            (root / 'config/source-contract.json').write_text(json.dumps(original))
            with self.assertRaises(ValueError):
                versions(root)

    def test_original_replay_has_separate_immutable_identity(self):
        pins=versions(Path(__file__).resolve().parents[1], include_replay=True)
        self.assertEqual(pins['frozen_replay'],'8534d90f801abff8ace07938f9cc104feeaac407')

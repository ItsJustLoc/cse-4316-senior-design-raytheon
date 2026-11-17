"""The NLP boundary only permits complete, recognized mission proposals."""

import unittest

from pydantic import ValidationError

from nlp.models import Interpretation, Mission, Target


class MissionTests(unittest.TestCase):
    def test_targeted_actions_preserve_target(self):
        for action in ("retrieve", "read_nfc"):
            with self.subTest(action=action):
                mission = Mission.model_validate({
                    "action": action,
                    "target": {"color": "blue", "object_type": "box"},
                })
                self.assertEqual(mission.target.color, "blue")

    def test_target_required_only_for_targeted_actions(self):
        for action in ("retrieve", "read_nfc"):
            with self.subTest(action=action), self.assertRaises(ValidationError):
                Mission(action=action, target=None)
        for action in ("stop", "return_to_start"):
            with self.subTest(action=action):
                self.assertIsNone(Mission(action=action, target=None).target)
                with self.assertRaises(ValidationError):
                    Mission(action=action, target=Target(color="red", object_type="cube"))

    def test_unknown_fields_actions_and_targets_are_rejected(self):
        invalid = (
            {"action": "drive", "target": None},
            {"action": "stop", "target": None, "speed": 10},
            {"action": "stop"},
            {"action": "retrieve", "target": {"color": "", "object_type": "cube"}},
            {"action": "retrieve", "target": {"color": 1, "object_type": "cube"}},
            {"action": "retrieve", "target": {"color": "red", "object_type": "person"}},
            {"action": "retrieve", "target": {
                "color": "red", "object_type": "cube", "coordinates": [1, 2],
            }},
        )
        for mission in invalid:
            with self.subTest(mission=mission), self.assertRaises(ValidationError):
                Mission.model_validate(mission)

    def test_ready_requires_a_mission_and_other_states_forbid_one(self):
        mission = Mission(action="stop", target=None)
        result = Interpretation(status="ready", mission=mission, message="Stop requested.")
        self.assertEqual(result.mission.action, "stop")
        with self.assertRaises(ValidationError):
            Interpretation(status="ready", mission=None, message="Stop requested.")
        for status in ("clarification_required", "rejected"):
            with self.subTest(status=status):
                result = Interpretation(status=status, mission=None, message="Specify a color.")
                self.assertIsNone(result.mission)
                with self.assertRaises(ValidationError):
                    Interpretation(status=status, mission=mission, message="Specify a color.")

    def test_blank_explanation_and_extra_output_fields_are_rejected(self):
        for fields in (
            {"status": "rejected", "mission": None, "message": "   "},
            {"status": "rejected", "mission": None, "message": "No.", "execute": True},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                Interpretation.model_validate(fields)

    def test_missions_cannot_be_mutated_after_validation(self):
        mission = Mission(action="stop", target=None)
        with self.assertRaises(ValidationError):
            mission.action = "drive"


if __name__ == "__main__":
    unittest.main()

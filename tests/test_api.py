import unittest

from retract.api import dispatch
from retract.models import ValidationError, NotFoundError
from retract.service import MemoryService
from tests.support import ModelStore


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.service = MemoryService(ModelStore())
        dispatch(self.service, "/projects", {"project_id": "project", "name": "Project"})

    def test_recall_empty_project_is_explicit_empty_context(self):
        result = dispatch(self.service, "/recall", {"project_id": "project", "scope": "web/main"})
        self.assertEqual(result["active_facts"], [])
        self.assertEqual(result["project_revision"], 0)

    def test_unknown_route_is_not_found(self):
        with self.assertRaises(NotFoundError):
            dispatch(self.service, "/unknown", {})

    def test_missing_or_unknown_inputs_are_validation_errors(self):
        for path, body in (("/recall", {}), ("/history", {}),
                           ("/projects", {"project_id": "project"}),
                           ("/recall", {"project_id": "project", "scope": "web/main", "unexpected": True})):
            with self.subTest(path=path), self.assertRaises(ValidationError):
                dispatch(self.service, path, body)

    def test_recall_subjects_must_be_a_list(self):
        for value in (False, 0, "", "subject", {}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                dispatch(self.service, "/recall", {"project_id": "project", "scope": "web/main", "subjects": value})

    def test_history_requires_exactly_one_target(self):
        for body in ({"project_id": "project"}, {"project_id": "project", "fact_id": "F1", "event_id": "U1"}):
            with self.subTest(body=body), self.assertRaises(ValidationError):
                dispatch(self.service, "/history", body)

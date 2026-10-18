from dataclasses import replace
import os
import unittest

from retract.models import ConflictError, PlanRevisionInput, ValidationError
from tests.test_policy import confirmed_update
from tests import test_service, test_integration


class PlanRevisionBehavior:
    def revision(self, **changes):
        return replace(PlanRevisionInput('account-settings', 'P1', 'P2',
            'Use cookie sessions and preserve own-profile checks', ['F5', 'F4'],
            'U1 replaced browser bearer tokens with cookies', True, 6), **changes)

    def test_revision_preserves_history_and_clears_warning(self):
        self.service.process_update(confirmed_update())
        request = self.revision()
        result = self.service.revise_plan(request)
        self.assertEqual(result['outcome'], 'revised')
        self.assertEqual(self.store.get('Plan', 'account-settings', 'P1')['status'], 'superseded')
        self.assertEqual(self.store.plan_dependencies('account-settings', 'P1'), ['F1', 'F4'])
        self.assertEqual(self.store.plan_dependencies('account-settings', 'P2'), ['F4', 'F5'])
        self.assertEqual(self.service.recall('account-settings', 'web-client/main')['affected_plans'], [])
        snapshot = self.service.dashboard('account-settings')
        self.assertTrue(any(e['relationship'] == 'REVISES' and e['to']['id'] == 'P1' for e in snapshot['edges']))
        self.assertEqual(snapshot['counts']['affected'], 0)
        self.assertEqual(self.service.revise_plan(request), result)
        self.assertEqual(self.service.project('account-settings')['revision'], 7)
        with self.assertRaises(ConflictError):
            self.service.revise_plan(replace(request, reason='Different reason'))
        with self.assertRaises(ConflictError):
            self.service.revise_plan(replace(request, replacement_plan_id='P3', expected_revision=7))

    def test_old_or_cross_project_dependencies_and_stale_reviews_rejected(self):
        self.service.process_update(confirmed_update())
        for changes in ({'dependency_fact_ids': ['F1']}, {'dependency_fact_ids': ['missing']}, {'expected_revision': 5}):
            with self.subTest(changes=changes), self.assertRaises(ConflictError):
                self.service.revise_plan(self.revision(**changes))
        self.assertEqual(self.service.project('account-settings')['revision'], 6)
        self.assertEqual(self.store.get('Plan', 'account-settings', 'P1')['status'], 'needs_review')
        with self.assertRaises(ValidationError):
            self.revision(confirmation=False)

    def test_later_correction_flags_current_version_only(self):
        self.service.process_update(confirmed_update())
        self.service.revise_plan(self.revision())
        first = confirmed_update()
        update = replace(first, event_id='U3', replacement_fact_id='F6', target_fact_id='F4', scope='account-service/main',
            source=replace(first.source, id='S-U3', content='Allow administrators to update profiles'),
            text='Allow administrators to update profiles',
            candidate=replace(first.candidate, subject='profile', predicate='ownership', value='owners and administrators', excerpt='Allow administrators to update profiles'))
        result = self.service.process_update(update)
        self.assertEqual(result['flagged_plan_ids'], ['P2'])
        self.assertEqual(self.store.get('Plan', 'account-settings', 'P1')['status'], 'superseded')


class PlanRevisionTests(PlanRevisionBehavior, unittest.TestCase):
    setUp = test_service.ServiceTests.setUp


@unittest.skipUnless(os.getenv('RUN_FALKORDB_TESTS') == '1', 'Requires real FalkorDB')
class PlanRevisionGraphTests(PlanRevisionBehavior, unittest.TestCase):
    setUp = test_integration.FalkorDBTests.setUp

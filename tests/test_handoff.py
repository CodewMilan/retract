from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import unittest

from retract.models import ClaimInput, ConflictError, HandoffInput, PlanRevisionInput, ValidationError
from tests.test_policy import confirmed_update
from tests import test_service, test_integration


class HandoffBehavior:
    def handoff(self, **changes):
        return replace(HandoffInput('account-settings', 'web-client/main', 'H1', 'agent-a', 'P1',
                                    'Settings form drafted; wire the save call and run tests', ['F1', 'F4']), **changes)

    def claim(self, agent='agent-b', **changes):
        return replace(ClaimInput('account-settings', 'H1', agent), **changes)

    def test_handoff_is_recalled_then_claimed_once(self):
        created = self.service.create_handoff(self.handoff(to_agent='agent-b'))
        self.assertEqual(created['outcome'], 'created')
        self.assertEqual(self.service.create_handoff(self.handoff(to_agent='agent-b'))['outcome'], 'duplicate')
        recalled = self.service.recall('account-settings', 'web-client/main')
        [item] = recalled['open_handoffs']
        self.assertEqual(item['handoff']['from_agent'], 'agent-a')
        self.assertFalse(item['stale'])
        self.assertEqual([fact['fact_id'] for fact in item['cited_facts']], ['F1', 'F4'])
        with self.assertRaises(ConflictError):
            self.service.claim_handoff(self.claim('agent-c'))
        claimed = self.service.claim_handoff(self.claim())
        self.assertEqual((claimed['outcome'], claimed['handoff']['claimed_by']), ('claimed', 'agent-b'))
        self.assertEqual(self.service.claim_handoff(self.claim())['outcome'], 'duplicate')
        self.assertEqual(self.service.recall('account-settings', 'web-client/main')['open_handoffs'], [])

    def test_claim_reports_superseded_facts_and_revised_plan(self):
        self.service.create_handoff(self.handoff())
        self.service.process_update(confirmed_update())
        stale = self.service.recall('account-settings', 'web-client/main')['open_handoffs'][0]
        self.assertTrue(stale['stale'])
        self.assertIn({'fact_id': 'F1', 'current_fact_id': 'F5', 'changed': True}, stale['cited_facts'])
        self.assertIn('Plan P1 needs review since this handoff was written', stale['warnings'])
        revision = self.service.project('account-settings')['revision']
        self.service.revise_plan(PlanRevisionInput('account-settings', 'P1', 'P2', 'Use cookie sessions',
                                                   ['F5', 'F4'], 'F1 replaced', True, revision))
        claimed = self.service.claim_handoff(self.claim())
        self.assertEqual(claimed['current_plan']['plan_id'], 'P2')
        self.assertIn('Plan P1 was revised; current version is P2', claimed['warnings'])
        self.assertIn('Fact F1 was superseded; current: F5', claimed['warnings'])

    def test_invalid_handoffs_and_claims_are_rejected(self):
        self.service.process_update(confirmed_update())
        for changes in ({'fact_ids': ['F1']}, {'fact_ids': ['missing']}, {'plan_id': 'missing'},
                        {'scope': 'cli-client/main'}):
            with self.subTest(changes=changes), self.assertRaises(ConflictError):
                self.service.create_handoff(self.handoff(**{'fact_ids': ['F5'], **changes}))
        with self.assertRaises(ValidationError):
            self.handoff(to_agent='agent-a')
        self.service.create_handoff(self.handoff(fact_ids=['F5']))
        with self.assertRaises(ConflictError):
            self.service.create_handoff(self.handoff(fact_ids=['F5'], note='Different note'))
        with self.assertRaises(ConflictError):
            self.service.claim_handoff(self.claim('agent-a'))

    def test_concurrent_claims_have_one_winner(self):
        self.service.create_handoff(self.handoff())

        def attempt(index):
            try:
                return self.service.claim_handoff(self.claim(f'agent-{index}'))['handoff']['claimed_by']
            except ConflictError:
                return None

        with ThreadPoolExecutor(8) as pool:
            winners = [name for name in pool.map(attempt, range(1, 9)) if name]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.store.get('Handoff', 'account-settings', 'H1')['claimed_by'], winners[0])


class HandoffTests(HandoffBehavior, unittest.TestCase):
    setUp = test_service.ServiceTests.setUp


@unittest.skipUnless(os.getenv('RUN_FALKORDB_TESTS') == '1', 'Requires real FalkorDB')
class HandoffGraphTests(HandoffBehavior, unittest.TestCase):
    setUp = test_integration.FalkorDBTests.setUp

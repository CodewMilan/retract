import json
import os
import unittest

from retract.agent import GroqDrafter, ReviewerAgent, TemplateDrafter
from retract.api import dispatch
from retract.inference import GroqInterpreter, ModelResponseError
from retract.mcp_tools import ApiError
from retract.models import ClaimInput, ConflictError, NotFoundError, PlanRevisionInput
from tests.test_inference import Transport, envelope
from tests.test_policy import confirmed_update
from tests import test_service, test_integration


class AgentBehavior:
    def api(self, route, body):
        self.calls.append(route)
        try:
            return dispatch(self.service, route, body)
        except ConflictError as exc:
            raise ApiError(str(exc), 409) from None
        except NotFoundError as exc:
            raise ApiError(str(exc), 404) from None

    def agent(self, drafter=None):
        self.calls = []
        return ReviewerAgent(self.api, drafter or TemplateDrafter())

    def test_nothing_to_do_before_a_correction(self):
        report = self.agent().run('account-settings', 'web-client/main')
        self.assertEqual(report['decisions'], [])
        self.assertNotIn('/handoffs', self.calls)

    def test_correction_flows_from_reviewer_to_coding_agent(self):
        self.service.process_update(confirmed_update())
        report = self.agent().run('account-settings', 'web-client/main')
        [decision] = report['decisions']
        self.assertEqual((decision['plan_id'], decision['action'], decision['to_agent']), ('P1', 'handed_off', 'codex'))
        self.assertEqual(decision['draft']['cited_fact_ids'], ['F4', 'F5'])
        self.assertIn('P1 depends on F1', decision['reason'])
        self.assertIn('replaced by F5', decision['reason'])
        self.assertIn({'fact_id': 'F1', 'current_fact_id': 'F5', 'changed': True}, decision['dependencies'])
        self.assertEqual(self.store.get('Plan', 'account-settings', 'P1')['status'], 'needs_review')
        self.assertEqual(self.store.get('Fact', 'account-settings', 'F1')['status'], 'superseded')

        recalled = self.service.recall('account-settings', 'web-client/main')
        [handoff] = recalled['open_handoffs']
        self.assertEqual(handoff['handoff']['to_agent'], 'codex')
        self.assertIn('cookie', handoff['handoff']['note'].lower())
        self.assertIn('Requires developer confirmation', handoff['handoff']['note'])
        self.assertTrue(handoff['stale'])
        self.assertEqual(handoff['warnings'], ['Plan P1 still needs review'])

        rerun = self.agent().run('account-settings', 'web-client/main')
        self.assertEqual((rerun['decisions'][0]['action'], rerun['decisions'][0]['reason']),
                         ('skipped', 'Already handed off (open for codex)'))
        self.assertNotIn('/handoffs', self.calls)

        with self.assertRaises(ConflictError):
            self.service.claim_handoff(ClaimInput('account-settings', decision['handoff_id'], 'other-agent'))
        claimed = self.service.claim_handoff(ClaimInput('account-settings', decision['handoff_id'], 'codex'))
        self.assertEqual(claimed['handoff']['claimed_by'], 'codex')
        [summary] = self.service.recall('account-settings', 'web-client/main')['affected_plans'][0]['handoffs']
        self.assertEqual((summary['status'], summary['claimed_by']), ('claimed', 'codex'))

        class NoModel:
            label = 'must-not-run'

            def draft(self, context):
                raise AssertionError('Claimed handoff must not trigger another draft')

        after_claim = self.agent(NoModel()).run('account-settings', 'web-client/main')
        self.assertEqual(after_claim['decisions'][0]['reason'], 'Already handed off (claimed by codex)')
        self.assertNotIn('/handoffs', self.calls)
        revision = self.service.project('account-settings')['revision']
        self.service.revise_plan(PlanRevisionInput('account-settings', 'P1', 'P2', decision['draft']['revised_plan'],
                                                   decision['draft']['cited_fact_ids'], 'Reviewer handoff accepted',
                                                   True, revision))
        self.assertEqual(self.agent().run('account-settings', 'web-client/main')['decisions'], [])

    def test_model_draft_is_used_and_validated(self):
        self.service.process_update(confirmed_update())
        draft = {'revised_plan': 'Use HTTP-only cookie sessions (F5); keep own-profile checks (F4).',
                 'rationale': 'F1 was replaced by F5.', 'cited_fact_ids': ['F5', 'F4']}
        transport = Transport(envelope(draft))
        report = self.agent(GroqDrafter(GroqInterpreter('test', opener=transport))).run('account-settings', 'web-client/main')
        decision = report['decisions'][0]
        self.assertEqual(report['drafter'], 'groq:openai/gpt-oss-20b')
        self.assertEqual(decision['draft']['cited_fact_ids'], ['F4', 'F5'])
        sent = json.loads(json.loads(transport.requests[0][0].data)['messages'][1]['content'])
        self.assertEqual(sent['current_fact_ids'], ['F4', 'F5'])
        self.assertEqual([change['old']['id'] for change in sent['changed']], ['F1'])
        self.assertEqual(sent['changed'][0]['new']['id'], 'F5')

    def test_model_citing_retired_fact_creates_no_handoff(self):
        self.service.process_update(confirmed_update())
        draft = {'revised_plan': 'Keep bearer tokens', 'rationale': 'x', 'cited_fact_ids': ['F1']}
        drafter = GroqDrafter(GroqInterpreter('test', opener=Transport(envelope(draft))))
        with self.assertRaises(ModelResponseError):
            self.agent(drafter).run('account-settings', 'web-client/main')
        self.assertEqual(self.service.recall('account-settings', 'web-client/main')['open_handoffs'], [])

    def test_unrelated_scope_is_left_alone(self):
        self.service.process_update(confirmed_update())
        self.assertEqual(self.agent().run('account-settings', 'cli-client/main')['decisions'], [])


class AgentTests(AgentBehavior, unittest.TestCase):
    setUp = test_service.ServiceTests.setUp


@unittest.skipUnless(os.getenv('RUN_FALKORDB_TESTS') == '1', 'Requires real FalkorDB')
class AgentGraphTests(AgentBehavior, unittest.TestCase):
    setUp = test_integration.FalkorDBTests.setUp

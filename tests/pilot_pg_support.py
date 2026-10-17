"""Reuses the approved disposable PostgreSQL harness; fixture data is opaque only."""
from mission_control.pilot_postgres import PilotStore, apply_pilot_migration
from tests import test_postgres_integration as base_pg
from tests.pilot_support import TENANT, JOURNEY, pilot_authority, pilot_contracts, pilot_references
from tests.synthetic_postgres_support import session_ref
from mission_control.synthetic_postgres import _query


class PilotFixture:
    setUpClass=classmethod(base_pg.PostgreSQLIntegrationTests.setUpClass.__func__)
    tearDownClass=classmethod(base_pg.PostgreSQLIntegrationTests.tearDownClass.__func__)

    def setUp(self):
        self.authority,self.custody=pilot_authority()
        self.store,self.admin=self.new_empty_store()
        self.journey,self.intake,self.departments,self.rules,self.events=pilot_contracts()
        for tenant in (TENANT,'syn-tenant-2'):
            with self.tx('policy_admin',tenant) as tx:
                tx.bootstrap_policy()
                for kind,reference,parent in pilot_references(tenant): tx.register_reference(kind,reference,parent)
                tx.commit()
        with self.tx() as tx:
            for department in self.departments: tx.append_department(department)
            for rule in self.rules: tx.append_rule(rule)
            tx.start_journey(self.journey,self.intake,'syn-start-key');tx.commit()
        with self.tx('approval_issuer') as tx:
            for department in self.departments: tx.issue_routing_approval('department',department.department_id,1,department.approval_reference)
            for rule in self.rules: tx.issue_routing_approval('rule',rule.rule_id,1,rule.approval_reference)
            tx.commit()

    def new_empty_store(self):
        base,admin=base_pg.PostgreSQLIntegrationTests.new_store(self)
        apply_pilot_migration(admin,self.authority,session_ref('migration_operator'),TENANT,1)
        return PilotStore(base.factory,self.authority,self.custody),admin

    def tx(self,role='data_writer',tenant=TENANT,store=None):
        reference='syn-session-reader-beta-'+tenant if role=='reader-beta' else session_ref(role,tenant)
        return (store or self.store).transaction(tenant,reference,1)

    def prepare(self,index=1,event=None,approve=True):
        event=event or self.events[index-1]
        with self.tx() as tx:
            tx.propose_event(event,event.revision-1,'syn-propose-'+event.event_id+'-'+str(event.revision));tx.commit()
        if approve:
            with self.tx('approval_issuer') as tx:
                tx.issue_event_approval(JOURNEY,event.event_id,event.revision,event.approval_reference);tx.commit()
        return event

    def advance(self,index=1,event=None,version=None,key=None,commit=True):
        event=event or self.events[index-1]
        with self.tx() as tx:
            result=tx.advance_event(JOURNEY,event.event_id,event.revision,index-1 if version is None else version,key or 'syn-advance-'+str(index).zfill(2))
            if commit: tx.commit()
        return result

    def stage(self,index=1,event=None):
        event=self.prepare(index,event)
        return self.advance(index,event)

    def complete_all(self):
        return [self.stage(index) for index in range(1,17)]

    def count(self,name):
        with self.admin() as connection:
            return _query(connection,'SELECT count(*) AS total FROM mc_syn.'+name+' WHERE tenant_reference=%s',(TENANT,))[0][0]['total']

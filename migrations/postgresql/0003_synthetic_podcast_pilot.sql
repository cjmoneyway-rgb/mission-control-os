-- Forward-only, inactive synthetic extension. No seed records or external actions.
CREATE TABLE mc_syn.pilot_journeys (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), reference text NOT NULL CHECK (reference LIKE 'syn-%'),
 intake_reference text NOT NULL, intake_kind text NOT NULL CHECK (intake_kind='intake'), intake_revision bigint NOT NULL CHECK (intake_revision=1),
 original_classification text NOT NULL CHECK (original_classification='syn-entry-class'), payload jsonb NOT NULL,
 content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'), state text NOT NULL CHECK (state='inactive'),
 actor_reference text NOT NULL, policy_revision bigint NOT NULL, created_at timestamptz NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,reference), UNIQUE (tenant_reference,intake_reference),
 CHECK (payload ?& ARRAY['state','tenant_reference','journey_id','original_classification','content_digest']),
 CHECK (payload->>'state'='inactive' AND payload->>'tenant_reference'=tenant_reference AND payload->>'journey_id'=reference
        AND payload->>'original_classification'=original_classification AND payload->>'content_digest'=content_digest),
 FOREIGN KEY (tenant_reference,intake_kind,intake_reference,intake_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision),
 FOREIGN KEY (tenant_reference,actor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference),
 FOREIGN KEY (tenant_reference,policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference,policy_revision)
);
CREATE TABLE mc_syn.pilot_proposals (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL,
 event_reference text NOT NULL CHECK (event_reference LIKE 'syn-%'), revision bigint NOT NULL CHECK (revision>0), previous_revision bigint,
 content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'), payload jsonb NOT NULL,
 state text NOT NULL CHECK (state='inactive'), actor_reference text NOT NULL, policy_revision bigint NOT NULL,
 created_at timestamptz NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference,event_reference,revision),
 UNIQUE (tenant_reference,journey_reference,event_reference,revision,content_digest),
 CHECK ((revision=1 AND previous_revision IS NULL) OR (revision>1 AND previous_revision=revision-1)),
 CHECK (payload ?& ARRAY['state','tenant_reference','journey_reference','event_id','revision','content_digest']),
 CHECK (payload->>'state'='inactive' AND payload->>'tenant_reference'=tenant_reference AND payload->>'journey_reference'=journey_reference
        AND payload->>'event_id'=event_reference AND (payload->>'revision')::bigint=revision AND payload->>'content_digest'=content_digest),
 FOREIGN KEY (tenant_reference,journey_reference) REFERENCES mc_syn.pilot_journeys (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference,previous_revision) REFERENCES mc_syn.pilot_proposals (tenant_reference,journey_reference,event_reference,revision),
 FOREIGN KEY (tenant_reference,actor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference),
 FOREIGN KEY (tenant_reference,policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference,policy_revision)
);
CREATE TABLE mc_syn.pilot_proposal_heads (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL,
 event_reference text NOT NULL, revision bigint NOT NULL CHECK (revision>0), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference,event_reference),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference,revision) REFERENCES mc_syn.pilot_proposals (tenant_reference,journey_reference,event_reference,revision)
);
CREATE TABLE mc_syn.pilot_evidence (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), reference text NOT NULL CHECK (reference LIKE 'syn-%'),
 journey_reference text NOT NULL, event_reference text NOT NULL, proposal_revision bigint NOT NULL, event_digest text NOT NULL,
 grantor_reference text NOT NULL, policy_revision bigint NOT NULL, valid_from timestamptz NOT NULL, expires_at timestamptz NOT NULL,
 proof jsonb NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,reference), CHECK (valid_from<expires_at),
 UNIQUE (tenant_reference,reference,journey_reference,event_reference,proposal_revision,event_digest),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference,proposal_revision,event_digest) REFERENCES mc_syn.pilot_proposals (tenant_reference,journey_reference,event_reference,revision,content_digest),
 FOREIGN KEY (tenant_reference,grantor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference),
 FOREIGN KEY (tenant_reference,policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference,policy_revision)
);
CREATE TABLE mc_syn.pilot_revocations (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), reference text NOT NULL, actor_reference text NOT NULL,
 created_at timestamptz NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'), PRIMARY KEY (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,reference) REFERENCES mc_syn.pilot_evidence (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,actor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference)
);
CREATE TABLE mc_syn.pilot_events (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL,
 sequence bigint NOT NULL CHECK (sequence>0), event_reference text NOT NULL, proposal_revision bigint NOT NULL, event_digest text NOT NULL,
 previous_sequence bigint, previous_digest text, content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
 original_classification text NOT NULL CHECK (original_classification='syn-entry-class'),
 stage_index bigint NOT NULL CHECK (stage_index BETWEEN 1 AND 16), disposition text NOT NULL CHECK (disposition IN ('accepted','blocked')),
 payload jsonb NOT NULL, state text NOT NULL CHECK (state='inactive'), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference,sequence), UNIQUE (tenant_reference,journey_reference,event_reference),
 UNIQUE (tenant_reference,journey_reference,sequence,content_digest),
 CHECK ((sequence=1 AND previous_sequence IS NULL AND previous_digest IS NULL) OR
        (sequence>1 AND previous_sequence=sequence-1 AND previous_digest IS NOT NULL)),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference,proposal_revision,event_digest) REFERENCES mc_syn.pilot_proposals (tenant_reference,journey_reference,event_reference,revision,content_digest),
 FOREIGN KEY (tenant_reference,journey_reference,previous_sequence,previous_digest) REFERENCES mc_syn.pilot_events (tenant_reference,journey_reference,sequence,content_digest)
);
CREATE TABLE mc_syn.pilot_heads (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL,
 version bigint NOT NULL CHECK (version>=0), completed_stage bigint NOT NULL CHECK (completed_stage BETWEEN 0 AND 16),
 last_event_reference text, progress text NOT NULL CHECK (progress IN ('pending','blocked','completed','closed')),
 state text NOT NULL CHECK (state='inactive'), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference),
 FOREIGN KEY (tenant_reference,journey_reference) REFERENCES mc_syn.pilot_journeys (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,journey_reference,last_event_reference) REFERENCES mc_syn.pilot_events (tenant_reference,journey_reference,event_reference),
 CHECK ((completed_stage=0 AND last_event_reference IS NULL) OR (completed_stage>0 AND last_event_reference IS NOT NULL)),
 CHECK ((completed_stage=16 AND progress IN ('completed','closed')) OR (completed_stage<16 AND progress IN ('pending','blocked')))
);
CREATE TABLE mc_syn.pilot_decisions (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL, event_reference text NOT NULL,
 reference text NOT NULL CHECK (reference LIKE 'syn-%'), classification text NOT NULL CHECK (classification LIKE 'syn-class-%'),
 rule_reference text NOT NULL, rule_revision bigint NOT NULL, rule_digest text NOT NULL, rule_kind text NOT NULL CHECK (rule_kind='rule'),
 approval_reference text NOT NULL, proposal_revision bigint NOT NULL, event_digest text NOT NULL,
 disposition text NOT NULL CHECK (disposition IN ('accepted','blocked')), reason_reference text NOT NULL,
 content_digest text NOT NULL, payload jsonb NOT NULL, state text NOT NULL CHECK (state='inactive'), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference,event_reference), UNIQUE (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference) REFERENCES mc_syn.pilot_events (tenant_reference,journey_reference,event_reference),
 FOREIGN KEY (tenant_reference,rule_kind,rule_reference,rule_revision,rule_digest) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision,content_digest),
 FOREIGN KEY (tenant_reference,approval_reference,journey_reference,event_reference,proposal_revision,event_digest) REFERENCES mc_syn.pilot_evidence (tenant_reference,reference,journey_reference,event_reference,proposal_revision,event_digest)
);
CREATE TABLE mc_syn.pilot_packet_links (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL, event_reference text NOT NULL,
 packet_reference text NOT NULL, packet_revision bigint NOT NULL CHECK (packet_revision=1), packet_kind text NOT NULL CHECK (packet_kind='packet'),
 state text NOT NULL CHECK (state='inactive'), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference,event_reference,packet_reference), UNIQUE (tenant_reference,packet_reference),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference) REFERENCES mc_syn.pilot_events (tenant_reference,journey_reference,event_reference),
 FOREIGN KEY (tenant_reference,packet_kind,packet_reference,packet_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision)
);
CREATE TABLE mc_syn.pilot_deliverables (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), journey_reference text NOT NULL, event_reference text NOT NULL,
 kind text NOT NULL CHECK (kind IN ('outcome','handoff')), reference text NOT NULL CHECK (reference LIKE 'syn-%'), packet_reference text NOT NULL,
 state text NOT NULL CHECK (state='inactive'), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,journey_reference,event_reference,kind,reference,packet_reference),
 FOREIGN KEY (tenant_reference,journey_reference,event_reference,packet_reference) REFERENCES mc_syn.pilot_packet_links (tenant_reference,journey_reference,event_reference,packet_reference)
);
CREATE FUNCTION mc_syn.check_pilot_head() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='pilot_heads' THEN
  IF NEW.tenant_reference<>OLD.tenant_reference OR NEW.journey_reference<>OLD.journey_reference OR NEW.version<>OLD.version+1
     OR OLD.completed_stage=16 OR NEW.completed_stage NOT IN (OLD.completed_stage,OLD.completed_stage+1) THEN
   RAISE EXCEPTION 'Synthetic pilot head must advance exactly once';
  END IF;
 ELSE
  IF NEW.tenant_reference<>OLD.tenant_reference OR NEW.journey_reference<>OLD.journey_reference
     OR NEW.event_reference<>OLD.event_reference OR NEW.revision<>OLD.revision+1 THEN
   RAISE EXCEPTION 'Synthetic proposal head must advance exactly once';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER pilot_head_step BEFORE UPDATE ON mc_syn.pilot_heads FOR EACH ROW EXECUTE FUNCTION mc_syn.check_pilot_head();
CREATE TRIGGER pilot_proposal_step BEFORE UPDATE ON mc_syn.pilot_proposal_heads FOR EACH ROW EXECUTE FUNCTION mc_syn.check_pilot_head();
REVOKE ALL ON FUNCTION mc_syn.check_pilot_head() FROM PUBLIC;
CREATE FUNCTION mc_syn.check_pilot_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE decision mc_syn.pilot_decisions%ROWTYPE; proposal jsonb; rule jsonb; completed bigint;
 original text; intake text; linked bigint; last_accepted text; missing boolean; expected_count bigint;
BEGIN
 SELECT original_classification,intake_reference INTO STRICT original,intake FROM mc_syn.pilot_journeys WHERE tenant_reference=NEW.tenant_reference AND reference=NEW.journey_reference;
 SELECT count(*) INTO completed FROM mc_syn.pilot_events WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND sequence<NEW.sequence AND disposition='accepted';
 SELECT event_reference INTO last_accepted FROM mc_syn.pilot_events WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND sequence<NEW.sequence AND disposition='accepted' ORDER BY sequence DESC LIMIT 1;
 SELECT * INTO STRICT decision FROM mc_syn.pilot_decisions WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND event_reference=NEW.event_reference;
 SELECT payload INTO STRICT proposal FROM mc_syn.pilot_proposals WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND event_reference=NEW.event_reference AND revision=NEW.proposal_revision;
 SELECT payload INTO STRICT rule FROM mc_syn.routing_records WHERE tenant_reference=NEW.tenant_reference AND kind='rule' AND reference=decision.rule_reference AND revision=decision.rule_revision;
 SELECT count(*) INTO linked FROM mc_syn.pilot_packet_links WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND event_reference=NEW.event_reference;
 IF NOT (proposal ?& ARRAY['stage_reference','previous_event_reference','dependency_references','outcome_references','handoff_references'])
 OR jsonb_typeof(proposal->'dependency_references') IS DISTINCT FROM 'array'
 OR jsonb_typeof(proposal->'outcome_references') IS DISTINCT FROM 'array'
 OR jsonb_typeof(proposal->'handoff_references') IS DISTINCT FROM 'array'
 OR jsonb_typeof(decision.payload->'packet_references') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION 'Incomplete synthetic event contract';
 END IF;
 SELECT EXISTS (SELECT 1 FROM jsonb_array_elements_text(proposal->'dependency_references') dep WHERE NOT EXISTS
  (SELECT 1 FROM mc_syn.pilot_events e WHERE e.tenant_reference=NEW.tenant_reference AND e.journey_reference=NEW.journey_reference AND e.sequence<NEW.sequence AND e.disposition='accepted' AND e.event_reference=dep)) INTO missing;
 IF NEW.original_classification<>original OR NEW.stage_index<>completed+1 OR NEW.stage_index>16
 OR proposal->>'stage_reference' IS DISTINCT FROM 'syn-stage-'||lpad(NEW.stage_index::text,2,'0')
 OR proposal->>'previous_event_reference' IS DISTINCT FROM last_accepted
 OR (last_accepted IS NOT NULL AND NOT (proposal->'dependency_references' ? last_accepted))
 OR decision.classification IS DISTINCT FROM 'syn-class-'||lpad(NEW.stage_index::text,2,'0')
 OR decision.disposition<>NEW.disposition OR (NEW.disposition='blocked') IS DISTINCT FROM missing
 OR (NEW.disposition='blocked' AND linked<>0) OR (NEW.disposition='accepted' AND linked<>jsonb_array_length(rule->'recipients'))
 OR jsonb_array_length(decision.payload->'packet_references')<>linked THEN
  RAISE EXCEPTION 'Synthetic lifecycle, classification or packet invariant failed';
 END IF;
 IF EXISTS (SELECT 1 FROM mc_syn.pilot_packet_links l JOIN mc_syn.routing_records p ON p.tenant_reference=l.tenant_reference AND p.kind='packet' AND p.reference=l.packet_reference AND p.revision=l.packet_revision
  WHERE l.tenant_reference=NEW.tenant_reference AND l.journey_reference=NEW.journey_reference AND l.event_reference=NEW.event_reference AND
   (p.payload->>'source_event_reference' IS DISTINCT FROM intake OR p.payload->>'original_classification' IS DISTINCT FROM original
    OR p.payload->>'current_classification' IS DISTINCT FROM decision.classification OR p.payload->>'rule_reference' IS DISTINCT FROM decision.rule_reference
    OR (p.payload->>'rule_revision')::bigint IS DISTINCT FROM decision.rule_revision OR p.payload->>'rule_digest' IS DISTINCT FROM decision.rule_digest
    OR NOT (decision.payload->'packet_references' ? l.packet_reference))) THEN
  RAISE EXCEPTION 'Synthetic packet belongs to a different event scope';
 END IF;
 IF NEW.disposition='accepted' AND EXISTS (SELECT 1 FROM jsonb_array_elements(rule->'recipients') recipient WHERE NOT EXISTS
  (SELECT 1 FROM mc_syn.pilot_packet_links l JOIN mc_syn.routing_records p ON p.tenant_reference=l.tenant_reference AND p.kind='packet' AND p.reference=l.packet_reference AND p.revision=l.packet_revision
   WHERE l.tenant_reference=NEW.tenant_reference AND l.journey_reference=NEW.journey_reference AND l.event_reference=NEW.event_reference AND p.payload->'recipient_references'=jsonb_build_array(recipient->>0))) THEN
  RAISE EXCEPTION 'Synthetic recipient packet missing';
 END IF;
 expected_count=linked*(jsonb_array_length(proposal->'outcome_references')+jsonb_array_length(proposal->'handoff_references'));
 IF (SELECT count(*) FROM mc_syn.pilot_deliverables WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND event_reference=NEW.event_reference)<>expected_count
 OR EXISTS (SELECT 1 FROM mc_syn.pilot_deliverables WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND event_reference=NEW.event_reference AND NOT
  (CASE WHEN kind='outcome' THEN proposal->'outcome_references' ELSE proposal->'handoff_references' END ? reference)) THEN
  RAISE EXCEPTION 'Synthetic outcome or handoff link missing';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pilot_event_integrity AFTER INSERT ON mc_syn.pilot_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mc_syn.check_pilot_event();
REVOKE ALL ON FUNCTION mc_syn.check_pilot_event() FROM PUBLIC;
DO $$ DECLARE name text;
BEGIN
 FOREACH name IN ARRAY ARRAY['pilot_journeys','pilot_proposals','pilot_proposal_heads','pilot_evidence','pilot_revocations','pilot_events','pilot_heads','pilot_decisions','pilot_packet_links','pilot_deliverables'] LOOP
  EXECUTE format('ALTER TABLE mc_syn.%I ENABLE ROW LEVEL SECURITY',name);
  EXECUTE format('ALTER TABLE mc_syn.%I FORCE ROW LEVEL SECURITY',name);
  EXECUTE format('CREATE POLICY tenant_scope ON mc_syn.%I TO "syn-runtime" USING (tenant_reference=current_setting(''mission_control.tenant'',true) AND dataset=''synthetic'') WITH CHECK (tenant_reference=current_setting(''mission_control.tenant'',true) AND dataset=''synthetic'')',name);
  EXECUTE format('GRANT SELECT,INSERT ON mc_syn.%I TO "syn-runtime"',name);
  EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.%I FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation()',name);
 END LOOP;
 FOREACH name IN ARRAY ARRAY['pilot_heads','pilot_proposal_heads'] LOOP
  EXECUTE format('DROP TRIGGER immutable_history ON mc_syn.%I',name);
  EXECUTE format('GRANT UPDATE ON mc_syn.%I TO "syn-runtime"',name);
  EXECUTE format('CREATE TRIGGER immutable_delete BEFORE DELETE ON mc_syn.%I FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation()',name);
 END LOOP;
END $$;
-- Read-only shared schema provenance only. No caller-controlled identifiers/SQL.
CREATE FUNCTION mc_syn.synthetic_migration_manifest() RETURNS jsonb
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT coalesce(jsonb_agg(jsonb_build_object('migration_id',migration_id,'checksum',checksum,'applied_at',applied_at) ORDER BY migration_id),'[]'::jsonb)
 FROM mc_syn.schema_migrations WHERE tenant_reference='syn-system' AND dataset='synthetic';
$$;
REVOKE ALL ON FUNCTION mc_syn.synthetic_migration_manifest() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mc_syn.synthetic_migration_manifest() TO "syn-runtime";

-- Inspect final transaction state, including restores and multiple events in one tx.
CREATE FUNCTION mc_syn.check_pilot_progress() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE head mc_syn.pilot_heads%ROWTYPE; total bigint; accepted bigint; last_accepted text;
 last_disposition text; terminal text; expected_progress text;
BEGIN
 SELECT * INTO STRICT head FROM mc_syn.pilot_heads WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference;
 SELECT count(*),count(*) FILTER (WHERE disposition='accepted') INTO total,accepted FROM mc_syn.pilot_events WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference;
 SELECT event_reference INTO last_accepted FROM mc_syn.pilot_events WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference AND disposition='accepted' ORDER BY sequence DESC LIMIT 1;
 SELECT disposition INTO last_disposition FROM mc_syn.pilot_events WHERE tenant_reference=NEW.tenant_reference AND journey_reference=NEW.journey_reference ORDER BY sequence DESC LIMIT 1;
 expected_progress=CASE WHEN last_disposition='blocked' THEN 'blocked' ELSE 'pending' END;
 IF accepted=16 THEN
  SELECT p.payload->>'terminal_reference' INTO STRICT terminal FROM mc_syn.pilot_events e JOIN mc_syn.pilot_proposals p ON p.tenant_reference=e.tenant_reference AND p.journey_reference=e.journey_reference AND p.event_reference=e.event_reference AND p.revision=e.proposal_revision
  WHERE e.tenant_reference=NEW.tenant_reference AND e.journey_reference=NEW.journey_reference AND e.event_reference=last_accepted;
  IF terminal NOT IN ('syn-completed','syn-closed') OR terminal IS NULL THEN RAISE EXCEPTION 'Synthetic terminal decision missing'; END IF;
  expected_progress=substring(terminal FROM 5);
 END IF;
 IF head.version<>total OR head.completed_stage<>accepted OR head.last_event_reference IS DISTINCT FROM last_accepted OR head.progress<>expected_progress THEN
  RAISE EXCEPTION 'Synthetic pilot head disagrees with preserved history';
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER pilot_progress_head AFTER INSERT OR UPDATE ON mc_syn.pilot_heads
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mc_syn.check_pilot_progress();
CREATE CONSTRAINT TRIGGER pilot_progress_event AFTER INSERT ON mc_syn.pilot_events
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mc_syn.check_pilot_progress();
REVOKE ALL ON FUNCTION mc_syn.check_pilot_progress() FROM PUBLIC;

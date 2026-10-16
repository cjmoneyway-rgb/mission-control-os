-- Forward-only, synthetic extension to mc_syn. No seeds or external actions.
CREATE TABLE mc_syn.routing_records (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
 kind text NOT NULL CHECK (kind IN ('department','rule','intake','packet')),
 reference text NOT NULL CHECK (reference LIKE 'syn-%'),
 revision bigint NOT NULL CHECK (revision > 0),
 previous_revision bigint,
 content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'),
 payload jsonb NOT NULL,
 state text NOT NULL CHECK (state = 'inactive'),
 actor_reference text NOT NULL,
 policy_revision bigint NOT NULL,
 created_at timestamptz NOT NULL,
 dataset text NOT NULL CHECK (dataset = 'synthetic'),
 PRIMARY KEY (tenant_reference,kind,reference,revision),
 UNIQUE (tenant_reference,kind,reference,revision,content_digest),
 CHECK ((revision=1 AND previous_revision IS NULL) OR previous_revision=revision-1),
 CHECK (kind <> 'intake' OR revision=1),
 CHECK (payload ?& ARRAY['state','tenant_reference','revision','content_digest']),
 CHECK (payload->>'state' = 'inactive' AND payload->>'tenant_reference' = tenant_reference
        AND (payload->>'revision')::bigint = revision AND payload->>'content_digest' = content_digest),
 FOREIGN KEY (tenant_reference,kind,reference,previous_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision),
 FOREIGN KEY (tenant_reference,actor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference),
 FOREIGN KEY (tenant_reference,policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference,policy_revision)
);
CREATE TABLE mc_syn.routing_heads (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), kind text NOT NULL, reference text NOT NULL,
 revision bigint NOT NULL CHECK (revision>0), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,kind,reference),
 FOREIGN KEY (tenant_reference,kind,reference,revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision)
);
-- Names are reserved permanently within a tenant; alias removal cannot reassign history.
CREATE TABLE mc_syn.routing_names (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), name text NOT NULL CHECK (name LIKE 'syn-%'),
 department_reference text NOT NULL, department_kind text NOT NULL DEFAULT 'department' CHECK (department_kind='department'),
 first_revision bigint NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,name),
 FOREIGN KEY (tenant_reference,department_kind,department_reference,first_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision)
);
CREATE TABLE mc_syn.routing_references (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), kind text NOT NULL,
 reference text NOT NULL CHECK (reference LIKE 'syn-%'), parent_reference text CHECK (parent_reference LIKE 'syn-%'),
 actor_reference text NOT NULL, policy_revision bigint NOT NULL,
 dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,kind,reference),
 CHECK (kind IN ('executive','team','escalation','visibility','mandate','classification','fact','action','policy','dependency','outcome','handoff')),
 FOREIGN KEY (tenant_reference,actor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference),
 FOREIGN KEY (tenant_reference,policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference,policy_revision)
);
CREATE TABLE mc_syn.routing_links (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'),
 packet_reference text NOT NULL, packet_revision bigint NOT NULL, packet_kind text NOT NULL CHECK (packet_kind='packet'),
 department_reference text NOT NULL, department_revision bigint NOT NULL, department_digest text NOT NULL,
 department_kind text NOT NULL CHECK (department_kind='department'),
 rule_reference text NOT NULL, rule_revision bigint NOT NULL, rule_digest text NOT NULL, rule_kind text NOT NULL CHECK (rule_kind='rule'),
 intake_reference text NOT NULL, intake_revision bigint NOT NULL CHECK (intake_revision=1), intake_kind text NOT NULL CHECK (intake_kind='intake'),
 dataset text NOT NULL CHECK (dataset='synthetic'), PRIMARY KEY (tenant_reference,packet_reference,packet_revision),
 FOREIGN KEY (tenant_reference,packet_kind,packet_reference,packet_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision),
 FOREIGN KEY (tenant_reference,department_kind,department_reference,department_revision,department_digest) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision,content_digest),
 FOREIGN KEY (tenant_reference,rule_kind,rule_reference,rule_revision,rule_digest) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision,content_digest),
 FOREIGN KEY (tenant_reference,intake_kind,intake_reference,intake_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision)
);
CREATE TABLE mc_syn.routing_evidence (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), reference text NOT NULL CHECK (reference LIKE 'syn-%'),
 kind text NOT NULL CHECK (kind IN ('department','rule')), record_reference text NOT NULL, record_revision bigint NOT NULL,
 content_digest text NOT NULL, grantor_reference text NOT NULL, policy_revision bigint NOT NULL,
 valid_from timestamptz NOT NULL, expires_at timestamptz NOT NULL, proof jsonb NOT NULL,
 dataset text NOT NULL CHECK (dataset='synthetic'), PRIMARY KEY (tenant_reference,reference),
 CHECK (valid_from<expires_at),
 FOREIGN KEY (tenant_reference,kind,record_reference,record_revision,content_digest) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision,content_digest),
 FOREIGN KEY (tenant_reference,grantor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference),
 FOREIGN KEY (tenant_reference,policy_revision) REFERENCES mc_syn.policy_revisions (tenant_reference,policy_revision)
);
CREATE TABLE mc_syn.routing_revocations (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), reference text NOT NULL,
 actor_reference text NOT NULL, created_at timestamptz NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,reference) REFERENCES mc_syn.routing_evidence (tenant_reference,reference),
 FOREIGN KEY (tenant_reference,actor_reference) REFERENCES mc_syn.subjects (tenant_reference,subject_reference)
);
CREATE TABLE mc_syn.routing_events (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), intake_reference text NOT NULL,
 intake_kind text NOT NULL CHECK (intake_kind='intake'), intake_revision bigint NOT NULL CHECK (intake_revision=1),
 sequence bigint NOT NULL CHECK (sequence>0), previous_sequence bigint, previous_digest text,
 content_digest text NOT NULL CHECK (content_digest ~ '^[0-9a-f]{64}$'), payload jsonb NOT NULL,
 state text NOT NULL CHECK (state='inactive'), dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,intake_reference,sequence),
 UNIQUE (tenant_reference,intake_reference,sequence,content_digest),
 CHECK ((sequence=1 AND previous_sequence IS NULL AND previous_digest IS NULL) OR
        (sequence>1 AND previous_sequence=sequence-1 AND previous_digest IS NOT NULL)),
 FOREIGN KEY (tenant_reference,intake_kind,intake_reference,intake_revision) REFERENCES mc_syn.routing_records (tenant_reference,kind,reference,revision),
 FOREIGN KEY (tenant_reference,intake_reference,previous_sequence,previous_digest) REFERENCES mc_syn.routing_events (tenant_reference,intake_reference,sequence,content_digest)
);
CREATE TABLE mc_syn.routing_journey_heads (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), intake_reference text NOT NULL,
 sequence bigint NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,intake_reference),
 FOREIGN KEY (tenant_reference,intake_reference,sequence) REFERENCES mc_syn.routing_events (tenant_reference,intake_reference,sequence)
);
CREATE TABLE mc_syn.routing_receipts (
 tenant_reference text NOT NULL CHECK (tenant_reference LIKE 'syn-%'), operation text NOT NULL CHECK (operation LIKE 'syn-%'),
 key text NOT NULL CHECK (key LIKE 'syn-%'), payload_digest text NOT NULL CHECK (payload_digest ~ '^[0-9a-f]{64}$'),
 result jsonb NOT NULL, dataset text NOT NULL CHECK (dataset='synthetic'),
 PRIMARY KEY (tenant_reference,operation,key)
);
CREATE FUNCTION mc_syn.check_routing_revision() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE prior jsonb;
BEGIN
 IF TG_TABLE_NAME='routing_heads' THEN
  IF NEW.revision<>OLD.revision+1 OR NEW.tenant_reference<>OLD.tenant_reference OR NEW.kind<>OLD.kind OR NEW.reference<>OLD.reference THEN
   RAISE EXCEPTION 'Synthetic head must advance exactly once';
  END IF;
 ELSIF TG_TABLE_NAME='routing_journey_heads' THEN
  IF NEW.sequence<>OLD.sequence+1 OR NEW.tenant_reference<>OLD.tenant_reference OR NEW.intake_reference<>OLD.intake_reference THEN
   RAISE EXCEPTION 'Synthetic journey must advance exactly once';
  END IF;
 ELSIF NEW.kind='packet' AND NEW.revision>1 THEN
  SELECT payload INTO STRICT prior FROM mc_syn.routing_records WHERE tenant_reference=NEW.tenant_reference AND kind='packet' AND reference=NEW.reference AND revision=1;
  IF (NEW.payload - ARRAY['revision','content_digest','current_classification','dependencies','priority','outcome_references','handoff_references']) IS DISTINCT FROM
     (prior - ARRAY['revision','content_digest','current_classification','dependencies','priority','outcome_references','handoff_references']) THEN
   RAISE EXCEPTION 'Original routing identity cannot change';
  END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER routing_revision BEFORE INSERT ON mc_syn.routing_records FOR EACH ROW EXECUTE FUNCTION mc_syn.check_routing_revision();
CREATE TRIGGER routing_head_step BEFORE UPDATE ON mc_syn.routing_heads FOR EACH ROW EXECUTE FUNCTION mc_syn.check_routing_revision();
CREATE TRIGGER routing_journey_step BEFORE UPDATE ON mc_syn.routing_journey_heads FOR EACH ROW EXECUTE FUNCTION mc_syn.check_routing_revision();
REVOKE ALL ON FUNCTION mc_syn.check_routing_revision() FROM PUBLIC;
DO $$ DECLARE name text;
BEGIN
 FOREACH name IN ARRAY ARRAY['routing_records','routing_heads','routing_names','routing_references','routing_links','routing_evidence','routing_revocations','routing_events','routing_journey_heads','routing_receipts'] LOOP
  EXECUTE format('ALTER TABLE mc_syn.%I ENABLE ROW LEVEL SECURITY',name);
  EXECUTE format('ALTER TABLE mc_syn.%I FORCE ROW LEVEL SECURITY',name);
  EXECUTE format('CREATE POLICY tenant_scope ON mc_syn.%I TO "syn-runtime" USING (tenant_reference=current_setting(''mission_control.tenant'',true) AND dataset=''synthetic'') WITH CHECK (tenant_reference=current_setting(''mission_control.tenant'',true) AND dataset=''synthetic'')',name);
  EXECUTE format('GRANT SELECT,INSERT ON mc_syn.%I TO "syn-runtime"',name);
  EXECUTE format('CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON mc_syn.%I FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation()',name);
 END LOOP;
 FOREACH name IN ARRAY ARRAY['routing_heads','routing_journey_heads'] LOOP
  EXECUTE format('DROP TRIGGER immutable_history ON mc_syn.%I',name);
  EXECUTE format('GRANT UPDATE ON mc_syn.%I TO "syn-runtime"',name);
  EXECUTE format('CREATE TRIGGER immutable_delete BEFORE DELETE ON mc_syn.%I FOR EACH ROW EXECUTE FUNCTION mc_syn.reject_history_mutation()',name);
 END LOOP;
END $$;

-- Deferred because a packet revision and its exact links are inserted together.
CREATE FUNCTION mc_syn.check_packet_routing_link() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked mc_syn.routing_links%ROWTYPE; source jsonb; department jsonb; rule jsonb;
BEGIN
 IF NEW.kind<>'packet' THEN RETURN NULL; END IF;
 SELECT * INTO linked FROM mc_syn.routing_links WHERE tenant_reference=NEW.tenant_reference AND packet_reference=NEW.reference AND packet_revision=NEW.revision;
 IF NOT FOUND THEN RAISE EXCEPTION 'Synthetic packet exact links required'; END IF;
 SELECT payload INTO STRICT source FROM mc_syn.routing_records WHERE tenant_reference=NEW.tenant_reference AND kind='intake' AND reference=linked.intake_reference AND revision=1;
 SELECT payload INTO STRICT department FROM mc_syn.routing_records WHERE tenant_reference=NEW.tenant_reference AND kind='department' AND reference=linked.department_reference AND revision=linked.department_revision;
 SELECT payload INTO STRICT rule FROM mc_syn.routing_records WHERE tenant_reference=NEW.tenant_reference AND kind='rule' AND reference=linked.rule_reference AND revision=linked.rule_revision;
 IF NEW.payload->>'source_event_reference' IS DISTINCT FROM linked.intake_reference
 OR NEW.payload->>'original_classification' IS DISTINCT FROM source->>'original_classification'
 OR NEW.payload->>'executive_reference' IS DISTINCT FROM department->>'executive_reference'
 OR NEW.payload->'recipient_references' IS DISTINCT FROM jsonb_build_array(linked.department_reference)
 OR (NEW.payload->>'registry_revision')::bigint IS DISTINCT FROM linked.department_revision
 OR NEW.payload->>'registry_digest' IS DISTINCT FROM linked.department_digest
 OR NEW.payload->>'rule_reference' IS DISTINCT FROM linked.rule_reference
 OR (NEW.payload->>'rule_revision')::bigint IS DISTINCT FROM linked.rule_revision
 OR NEW.payload->>'rule_digest' IS DISTINCT FROM linked.rule_digest
 OR NEW.payload->>'required_action' IS DISTINCT FROM rule->>'required_action'
 OR NEW.payload->>'decision_reference' IS DISTINCT FROM rule->>'approval_reference'
 OR NEW.payload->'visibility_references' IS DISTINCT FROM rule->'visibility_references'
 OR NOT (rule->'recipients' @> jsonb_build_array(jsonb_build_array(linked.department_reference,linked.department_revision,linked.department_digest,department->>'executive_reference')))
 THEN RAISE EXCEPTION 'Synthetic packet source or routing link mismatch'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER routing_packet_links AFTER INSERT ON mc_syn.routing_records
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION mc_syn.check_packet_routing_link();
REVOKE ALL ON FUNCTION mc_syn.check_packet_routing_link() FROM PUBLIC;

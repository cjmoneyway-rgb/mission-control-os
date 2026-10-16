"""Synthetic JSON export/restore proof. Not encrypted production backup or PITR."""
from dataclasses import asdict
from datetime import datetime
import os
from pathlib import Path
import re
import tempfile

from .contracts import Approval, digest
from .json_io import strict_json_loads
from .registry_persistence import validate_event_append
from .synthetic_identity import canonical, canonical_bytes, fingerprint, synthetic_reference
from .synthetic_postgres import (ENTITIES, LOGICAL_PATH, SQL_PATH, event_from,
                                 packet_from, registry_from, transactional_operation)


def migration_checksum():
    return fingerprint({'sql':SQL_PATH.read_text(),'logical':strict_json_loads(LOGICAL_PATH.read_text())})


@transactional_operation
def export_snapshot(tx, custody):
    actor,_ = tx._auth('backup.export','syn-backup')
    tables = {name:sorted([canonical(row) for row in tx._select(name)],key=canonical_bytes) for name in ENTITIES}
    payload = {'format':'syn-postgres-export-v1','dataset':'synthetic','tenant':tx.tenant,
               'migration_checksum':migration_checksum(),'tables':tables}
    validate_payload(payload,custody)
    return {'payload':payload,'checksum':fingerprint(payload),'proof':custody.seal(payload)}


def validate_archive(archive,custody):
    if not isinstance(archive,dict) or set(archive) != {'payload','checksum','proof'}:
        raise ValueError('Malformed synthetic archive')
    if archive['checksum'] != fingerprint(archive['payload']) or not custody.verify(archive['payload'],archive['proof']):
        raise ValueError('Archive signature or checksum mismatch')
    validate_payload(archive['payload'],custody)
    return archive['payload']


def validate_payload(payload,custody):
    if not isinstance(payload,dict) or set(payload) != {'format','dataset','tenant','migration_checksum','tables'}:
        raise ValueError('Malformed archive manifest')
    synthetic_reference(payload['tenant'])
    if (payload['format'] != 'syn-postgres-export-v1' or payload['dataset'] != 'synthetic'
            or payload['migration_checksum'] != migration_checksum()
            or not isinstance(payload['tables'],dict) or set(payload['tables']) != set(ENTITIES)):
        raise ValueError('Archive scope or migration mismatch')
    tables = payload['tables']
    indices = {}
    for name,entity in ENTITIES.items():
        if not isinstance(tables[name],list):
            raise ValueError('Malformed archive table')
        for key in [entity['primary_key']] + entity['unique_keys']:
            seen = set()
            for row in tables[name]:
                if not isinstance(row,dict) or set(row) != set(entity['columns']):
                    raise ValueError('Archive row schema mismatch')
                if row['tenant_reference'] != payload['tenant'] or row['dataset'] != 'synthetic':
                    raise ValueError('Cross-tenant or operational archive row')
                for column,kind in entity['columns'].items():
                    value = row[column]
                    if kind == 'integer' and (type(value) is not int or value < (0 if column=='previous_revision' else 1)):
                        raise ValueError('Invalid integer column')
                    if kind == 'reference' and (not isinstance(value,str) or not value.strip()):
                        raise ValueError('Invalid reference column')
                    if kind in ('digest','nullable_digest') and not (kind=='nullable_digest' and value is None):
                        if not isinstance(value,str) or re.fullmatch('[0-9a-f]{64}',value) is None:
                            raise ValueError('Invalid archive digest')
                    if kind == 'boolean' and type(value) is not bool:
                        raise ValueError('Invalid boolean column')
                    if kind == 'timestamp':
                        parsed = datetime.fromisoformat(value)
                        if parsed.tzinfo is None or parsed.utcoffset() is None:
                            raise ValueError('Archive timestamp timezone required')
                    if kind == 'json' and not isinstance(value,dict):
                        raise ValueError('Structured archive payload required')
                if 'state' in row and row['state'] not in ('draft','inactive'):
                    raise ValueError('Operational archive state forbidden')
                if 'active' in row and row['active'] is not False:
                    raise ValueError('Active archive event forbidden')
                if 'schema_revision' in row and row['schema_revision'] != 1:
                    raise ValueError('Unknown row schema')
                if 'previous_revision' in row and row['previous_revision'] != row['revision']-1:
                    raise ValueError('Revision lineage mismatch')
                if 'valid_from' in row and datetime.fromisoformat(row['valid_from']) >= datetime.fromisoformat(row['expires_at']):
                    raise ValueError('Invalid evidence/policy interval')
                identity = tuple(row[column] for column in key)
                if identity in seen:
                    raise ValueError('Duplicate archive key')
                seen.add(identity)
            indices[(name,tuple(key))] = seen
    for name,entity in ENTITIES.items():
        for fk in entity['foreign_keys']:
            target = indices[(fk['target'],tuple(fk['target_columns']))]
            for row in tables[name]:
                if tuple(row[column] for column in fk['columns']) not in target:
                    raise ValueError('Broken archive foreign key')
    for row in tables['policy_revisions']:
        document = row['rules_document']
        if (fingerprint(document) != row['content_digest'] or document.get('tenant') != payload['tenant']
                or document.get('revision') != row['policy_revision']
                or document.get('valid_from') != row['valid_from'] or document.get('expires_at') != row['expires_at']):
            raise ValueError('Policy archive integrity mismatch')
    registries = {}
    for row in tables['registry_revisions']:
        revision = registry_from(row['payload'])
        if (revision.tenant_reference,revision.record.record_id,revision.record.revision,revision.content_digest,revision.previous_revision,revision.schema_revision,revision.record.state) != (payload['tenant'],row['record_reference'],row['revision'],row['content_digest'],row['previous_revision'],row['schema_revision'],row['state']):
            raise ValueError('Registry archive content mismatch')
        registries[(row['record_reference'],row['revision'])] = revision
    packets = {}
    for row in tables['packet_revisions']:
        packet = packet_from(row['payload'])
        registry = registries[(packet.packet.registry_reference,packet.packet.registry_revision)]
        packet.validate(registry)
        if (packet.tenant_reference,packet.packet.packet_id,packet.revision,packet.packet.registry_reference,
                packet.packet.registry_revision,fingerprint(asdict(packet)),packet.previous_revision,packet.schema_revision,packet.packet.state) != (payload['tenant'],row['packet_reference'],row['revision'],row['registry_reference'],row['registry_revision'],row['content_digest'],row['previous_revision'],row['schema_revision'],row['state']):
            raise ValueError('Packet archive content mismatch')
        packets[(row['packet_reference'],row['revision'])] = packet
    journeys = {}
    for row in sorted(tables['journey_events'],key=lambda r:(r['journey_reference'],r['sequence'])):
        event = event_from(row['payload'])
        packet = packets[(event.event.packet.packet_id,event.packet_revision)]
        registry = registries[(packet.packet.registry_reference,packet.packet.registry_revision)]
        if (event.tenant_reference,event.event.event_id,event.event.journey_reference,event.sequence,event.packet_revision,event.previous_digest,event.content_digest,event.event.packet.packet_id,event.schema_revision) != (payload['tenant'],row['event_reference'],row['journey_reference'],row['sequence'],row['packet_revision'],row['previous_digest'],row['content_digest'],row['packet_reference'],row['schema_revision']):
            raise ValueError('Event archive content mismatch')
        validate_event_append(event,journeys.get(row['journey_reference']),None,packet,registry)
        journeys[row['journey_reference']] = event
    for data,heads,ref,revision in (('registry_revisions','registry_heads','record_reference','revision'),
                                    ('packet_revisions','packet_heads','packet_reference','revision'),
                                    ('journey_events','journey_heads','journey_reference','sequence')):
        expected = {}
        for row in tables[data]:
            expected[row[ref]] = max(expected.get(row[ref],0),row[revision])
        actual = {row[ref]:row[revision] for row in tables[heads]}
        if expected != actual:
            raise ValueError('Archive head mismatch')
        if data != 'journey_events':
            for resource,head in expected.items():
                versions = sorted(row[revision] for row in tables[data] if row[ref]==resource)
                if versions != list(range(1,head+1)):
                    raise ValueError('Missing historical revision')
    for row in tables['approval_evidence']:
        revision = registries[(row['record_reference'],row['record_revision'])]
        Approval(row['record_reference'],row['record_revision'],row['content_digest'],row['evidence_reference']).validate(revision.record.record_id,revision.record.revision,revision.record.payload())
        proof = strict_json_loads(row['proof_reference'])
        signed = {key:value for key,value in row.items() if key not in ('dataset','proof_reference')}
        if not custody.verify(signed,proof):
            raise ValueError('Approval evidence integrity failure')
        author = next(item['actor_reference'] for item in tables['registry_revisions'] if item['record_reference']==row['record_reference'] and item['revision']==row['record_revision'])
        if author == row['grantor_reference']:
            raise ValueError('Self-approved evidence forbidden')
    for row in tables['idempotency_receipts']:
        operation = row['operation_reference']
        if operation == 'registry.append_draft':
            item = registries[(row['result_reference'],row['result_revision'])]
        elif operation == 'packet.append_inactive':
            item = packets[(row['result_reference'],row['result_revision'])]
        elif operation == 'journey.append_inactive':
            candidates = [entry for entry in tables['journey_events'] if entry['journey_reference']==row['result_reference'] and entry['sequence']==row['result_revision']]
            item = event_from(candidates[0]['payload'])
        else:
            raise ValueError('Unknown receipt operation')
        if fingerprint(asdict(item)) != row['payload_digest']:
            raise ValueError('Receipt result digest mismatch')


def write_archive(path,archive,custody):
    validate_archive(archive,custody)
    target = Path(path)
    fd,name = tempfile.mkstemp(prefix='.syn-export-',dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(canonical_bytes(archive))
            handle.flush()
            os.fsync(handle.fileno())
        # Atomic no-replace publication; never overwrite another export/file.
        os.link(temporary,target,follow_symlinks=False)
        directory = os.open(target.parent,os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def read_archive(path,custody):
    archive = strict_json_loads(Path(path).read_text(encoding='utf-8'))
    validate_archive(archive,custody)
    return archive


@transactional_operation
def restore_snapshot(tx,archive,custody):
    actor,_ = tx._auth('backup.restore','syn-backup',context=False)
    payload = validate_archive(archive,custody)
    if payload['tenant'] != tx.tenant:
        raise PermissionError('Cross-tenant restore forbidden')
    if any(tx._select(table) for table in ENTITIES):
        raise ValueError('Restore target must be empty; merge/overwrite is forbidden')
    for table in ENTITIES:  # Dependency order in approved logical model.
        for row in payload['tables'][table]:
            tx._insert(table,row)
    # Restored policy must match the separately trusted current authority.
    tx._auth('backup.restore','syn-backup')
    tx._audit('backup.restore','syn-backup',actor)
    # Caller must request commit. Any error or clean exit without commit rolls back.

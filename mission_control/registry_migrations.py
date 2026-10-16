"""Validate backend-neutral migration manifests; never execute DDL or seed records."""
from dataclasses import dataclass
from pathlib import Path
import json
import re

from .contracts import digest, text
from .json_io import strict_json_loads

_TYPES = {'reference', 'integer', 'digest', 'timestamp', 'json', 'boolean', 'nullable_digest'}
_RULES = {'append_only', 'synthetic_only', 'inactive_only', 'positive_revision',
          'tenant_isolation', 'validity_interval', 'compare_and_swap'}


@dataclass(frozen=True)
class LogicalMigration:
    canonical_document: str

    @property
    def manifest(self):
        # Return a new document so a caller cannot mutate a validated plan.
        return strict_json_loads(self.canonical_document)

    @property
    def checksum(self):
        return digest(self.manifest)


def load_migration(path: Path | str) -> LogicalMigration:
    return validate_migration(strict_json_loads(Path(path).read_text(encoding='utf-8')))


def validate_migration(document) -> LogicalMigration:
    if not isinstance(document, dict) or set(document) != {
            'migration_id', 'from_revision', 'to_revision', 'dataset', 'entities'}:
        raise ValueError('Malformed migration manifest')
    text(document['migration_id'])
    if (type(document['from_revision']) is not int or type(document['to_revision']) is not int
            or document['from_revision'] != 0 or document['to_revision'] != 1
            or document['dataset'] != 'synthetic'):
        raise ValueError('Only initial inactive synthetic migration is supported')
    entities = document['entities']
    if not isinstance(entities, list) or not entities:
        raise ValueError('Migration needs entities')
    indexed = {}
    for entity in entities:
        if not isinstance(entity, dict) or set(entity) != {
                'name', 'columns', 'primary_key', 'unique_keys', 'foreign_keys', 'rules'}:
            raise ValueError('Malformed entity definition')
        name = entity['name']
        text(name)
        if re.fullmatch(r'[a-z][a-z0-9_]*', name) is None:
            raise ValueError('Invalid entity identifier')
        if name in indexed:
            raise ValueError('Duplicate entity')
        columns = entity['columns']
        if not isinstance(columns, dict) or not columns:
            raise ValueError('Missing columns')
        for column, kind in columns.items():
            text(column)
            if re.fullmatch(r'[a-z][a-z0-9_]*', column) is None:
                raise ValueError('Invalid column identifier')
            if not isinstance(kind, str) or kind not in _TYPES:
                raise ValueError('Unsupported column type')
        if columns.get('dataset') != 'reference':
            raise ValueError('Synthetic dataset discriminator is required')
        if columns.get('tenant_reference') != 'reference':
            raise ValueError('Every entity must be tenant-scoped')
        if not isinstance(entity['unique_keys'], list):
            raise ValueError('Invalid unique keys')
        for key in [entity['primary_key']] + entity['unique_keys']:
            if (not isinstance(key, list) or not key or
                    any(not isinstance(c, str) for c in key) or len(set(key)) != len(key) or
                    'tenant_reference' not in key or any(c not in columns for c in key)):
                raise ValueError('Keys must exist and be tenant-scoped')
        rules = entity['rules']
        if (not isinstance(rules, list) or not rules or
                any(not isinstance(rule, str) or rule not in _RULES for rule in rules) or
                not {'tenant_isolation', 'synthetic_only'} <= set(rules)):
            raise ValueError('Missing mandatory migration safety rules')
        if ('state' in columns or 'active' in columns) and 'inactive_only' not in rules:
            raise ValueError('Operational states are forbidden')
        if not isinstance(entity['foreign_keys'], list):
            raise ValueError('Invalid foreign keys')
        indexed[name] = entity
    required_entities = {'schema_migrations', 'subjects', 'policy_revisions', 'role_bindings',
                         'registry_revisions', 'registry_heads', 'approval_evidence',
                         'approval_revocations', 'packet_revisions', 'packet_heads',
                         'journey_events', 'journey_heads', 'idempotency_receipts', 'security_decisions'}
    if set(indexed) != required_entities:
        raise ValueError('Incomplete initial migration')
    history = {'schema_migrations', 'policy_revisions', 'registry_revisions',
               'approval_evidence', 'approval_revocations', 'packet_revisions',
               'journey_events', 'idempotency_receipts', 'security_decisions'}
    for name in history:
        if 'append_only' not in indexed[name]['rules']:
            raise ValueError('History entities must be append-only')
    for name in ('registry_heads', 'packet_heads', 'journey_heads'):
        if 'compare_and_swap' not in indexed[name]['rules']:
            raise ValueError('Head updates require compare-and-swap')
    essential = {
        'registry_revisions': {'record_reference', 'revision', 'previous_revision',
                               'state', 'payload', 'content_digest', 'schema_revision'},
        'packet_revisions': {'packet_reference', 'revision', 'previous_revision',
                             'registry_reference', 'registry_revision', 'state',
                             'payload', 'content_digest', 'schema_revision'},
        'journey_events': {'event_reference', 'journey_reference', 'sequence',
                           'packet_reference', 'packet_revision', 'previous_digest',
                           'content_digest', 'payload', 'active', 'schema_revision'},
    }
    for name, columns in essential.items():
        if not columns <= set(indexed[name]['columns']):
            raise ValueError('Missing versioned persistence columns')
    for entity in entities:
        for fk in entity['foreign_keys']:
            if not isinstance(fk, dict) or set(fk) != {'columns', 'target', 'target_columns'}:
                raise ValueError('Malformed foreign key')
            if not isinstance(fk['target'], str) or fk['target'] not in indexed:
                raise ValueError('Unknown foreign entity')
            columns, target_columns = fk['columns'], fk['target_columns']
            target = indexed[fk['target']]
            if (not isinstance(columns, list) or not isinstance(target_columns, list) or
                    not columns or len(columns) != len(target_columns) or
                    any(not isinstance(c, str) or c not in entity['columns'] for c in columns) or
                    any(not isinstance(c, str) or c not in target['columns'] for c in target_columns) or
                    len(set(columns)) != len(columns) or len(set(target_columns)) != len(target_columns) or
                    target_columns not in [target['primary_key']] + target['unique_keys']):
                raise ValueError('Foreign key must resolve to a unique key')
            if ('tenant_reference', 'tenant_reference') not in list(zip(columns, target_columns)):
                raise ValueError('Cross-tenant foreign keys are forbidden')
            if any(entity['columns'][a] != target['columns'][b] for a, b in zip(columns, target_columns)):
                raise ValueError('Foreign key type mismatch')
    return LogicalMigration(json.dumps(document, sort_keys=True, allow_nan=False))

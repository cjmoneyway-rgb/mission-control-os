"""Complete tenant-scoped synthetic snapshot; no production backup/key service."""
from datetime import datetime
import os
from pathlib import Path
import tempfile

from .json_io import strict_json_loads
from .pilot_postgres import PILOT_COLUMNS, SQL_PATH as PILOT_SQL
from .routing_postgres import COLUMNS, SQL_PATH as ROUTING_SQL
from .synthetic_archive import migration_checksum, validate_payload as validate_baseline
from .synthetic_identity import SyntheticEvidenceCustody, canonical, canonical_bytes, fingerprint
from .synthetic_postgres import ENTITIES, ROOT, _query, transactional_operation

MANIFEST_PATH=ROOT/'migrations/protected_registry/0003_archive_manifest.json'
MANIFEST=strict_json_loads(MANIFEST_PATH.read_text())
TABLES=MANIFEST['tables']
INSERT_ORDER=(*ENTITIES,'routing_records','routing_heads','routing_names','routing_references','routing_links',
              'routing_evidence','routing_revocations','routing_events','routing_journey_heads','routing_receipts',
              'pilot_journeys','pilot_proposals','pilot_proposal_heads','pilot_evidence','pilot_revocations','pilot_events',
              'pilot_heads','pilot_decisions','pilot_packet_links','pilot_deliverables')
assert set(INSERT_ORDER)==set(TABLES) and len(INSERT_ORDER)==len(TABLES)


def migration_checksums():
    return {'syn-postgresql-0001':migration_checksum(),'syn-postgresql-0002':fingerprint(ROUTING_SQL.read_text()),
            'syn-postgresql-0003':fingerprint(PILOT_SQL.read_text())}


def schema_descriptor(connection):
    relations,_=_query(connection,"SELECT c.relname AS name,c.relrowsecurity AS rls,c.relforcerowsecurity AS forced FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='mc_syn' AND c.relkind IN ('r','p','v','m','f','S')")
    if {row['name'] for row in relations}!=set(TABLES) or any(not row['rls'] or not row['forced'] for row in relations):
        raise ValueError('Incomplete, unknown or unprotected synthetic schema')
    descriptor={}
    for name in sorted(TABLES):
        columns,_=_query(connection,"SELECT column_name,udt_name,is_nullable FROM information_schema.columns WHERE table_schema='mc_syn' AND table_name=%s ORDER BY ordinal_position",(name,))
        constraints,_=_query(connection,"""SELECT c.contype AS kind,
            ARRAY(SELECT a.attname FROM unnest(c.conkey) WITH ORDINALITY AS k(id,ord) JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.id ORDER BY k.ord) AS columns,
            CASE WHEN c.contype='f' THEN (SELECT relname FROM pg_class WHERE oid=c.confrelid) ELSE NULL END AS target,
            ARRAY(SELECT a.attname FROM unnest(c.confkey) WITH ORDINALITY AS k(id,ord) JOIN pg_attribute a ON a.attrelid=c.confrelid AND a.attnum=k.id ORDER BY k.ord) AS target_columns
            FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='mc_syn' AND t.relname=%s AND c.contype IN ('p','u','f') ORDER BY c.contype,c.conname""",(name,))
        descriptor[name]={'columns':{row['column_name']:{'type':row['udt_name'],'nullable':row['is_nullable']=='YES'} for row in columns},
                          'keys':[row['columns'] for row in constraints if row['kind'] in ('p','u')],
                          'foreign_keys':[{key:row[key] for key in ('columns','target','target_columns')} for row in constraints if row['kind']=='f']}
    if descriptor!=TABLES: raise ValueError('Synthetic schema differs from reviewed archive manifest')
    return descriptor


def _provenance(connection):
    rows,_=_query(connection,'SELECT mc_syn.synthetic_migration_manifest() AS migrations')
    provenance=canonical(rows[0]['migrations'])
    if {row['migration_id']:row['checksum'] for row in provenance}!=migration_checksums() or len(provenance)!=3:
        raise ValueError('Unknown or mismatched installed migration provenance')
    return provenance


def _validate_structure(payload):
    if set(payload)!={'format','dataset','tenant','manifest_digest','migrations','tables','table_digests'}:
        raise ValueError('Unknown complete archive fields')
    if payload['format']!='syn-pilot-export-v1' or payload['dataset']!='synthetic' or payload['manifest_digest']!=fingerprint(MANIFEST):
        raise ValueError('Complete archive scope mismatch')
    from .department_routing import ref
    ref(payload['tenant'])
    if (not isinstance(payload['migrations'],list) or len(payload['migrations'])!=3
            or any(set(row)!={'migration_id','checksum','applied_at'} for row in payload['migrations'])
            or {row['migration_id']:row['checksum'] for row in payload['migrations']}!=migration_checksums()):
        raise ValueError('Archive migration provenance mismatch')
    for row in payload['migrations']:
        if datetime.fromisoformat(row['applied_at']).tzinfo is None: raise ValueError('Missing provenance timezone')
    tables=payload['tables']
    if not isinstance(tables,dict) or set(tables)!=set(TABLES) or set(payload['table_digests'])!=set(TABLES):
        raise ValueError('Complete archive must cover every reviewed table')
    indices={}
    for name,schema in TABLES.items():
        rows=tables[name]
        if not isinstance(rows,list) or fingerprint(rows)!=payload['table_digests'][name]: raise ValueError('Archive table digest mismatch')
        for row in rows:
            if not isinstance(row,dict) or set(row)!=set(schema['columns']): raise ValueError('Archive row column mismatch')
            if row['tenant_reference']!=payload['tenant'] or row['dataset']!='synthetic': raise ValueError('Cross-tenant or operational archive row')
            for column,meta in schema['columns'].items():
                value=row[column];kind=meta['type']
                if value is None:
                    if not meta['nullable']: raise ValueError('Missing required archive value')
                elif kind in ('int8','int4'):
                    if type(value) is not int: raise ValueError('Invalid archive integer')
                elif kind=='bool':
                    if type(value) is not bool: raise ValueError('Invalid archive boolean')
                elif kind=='text':
                    if not isinstance(value,str) or not value: raise ValueError('Invalid archive text')
                elif kind=='timestamptz':
                    if not isinstance(value,str) or datetime.fromisoformat(value).tzinfo is None: raise ValueError('Invalid archive timestamp')
                elif kind=='jsonb':
                    if not isinstance(value,(dict,list)): raise ValueError('Invalid archive JSON structure')
                else: raise ValueError('Unknown archive SQL type')
            allowed_states=('draft','inactive') if name in ENTITIES else ('inactive',)
            if 'state' in row and row['state'] not in allowed_states: raise ValueError('Operational or unsupported state forbidden')
            if 'active' in row and row['active'] is not False: raise ValueError('Operational event forbidden')
        for key in schema['keys']:
            entries=[tuple(row[column] for column in key) for row in rows]
            if len(set(entries))!=len(entries): raise ValueError('Duplicate archive key')
            indices[(name,tuple(key))]=set(entries)
    if tables['schema_migrations']: raise ValueError('Tenant archive cannot import shared schema ledger records')
    for name,schema in TABLES.items():
        for fk in schema['foreign_keys']:
            target=indices[(fk['target'],tuple(fk['target_columns']))]
            for row in tables[name]:
                identity=tuple(row[column] for column in fk['columns'])
                if not any(value is None for value in identity) and identity not in target: raise ValueError('Broken complete archive reference')


def validate_complete_archive(archive,custody):
    try:
        if type(custody) is not SyntheticEvidenceCustody or not isinstance(archive,dict) or set(archive)!={'payload','checksum','proof'}:
            raise ValueError('Untrusted archive envelope')
        payload=archive['payload']
        if not isinstance(payload,dict) or archive['checksum']!=fingerprint(payload) or not custody.verify(payload,archive['proof']):
            raise ValueError('Unverifiable complete archive')
        _validate_structure(payload)
        validate_baseline({'format':'syn-postgres-export-v1','dataset':'synthetic','tenant':payload['tenant'],
                           'migration_checksum':migration_checksum(),'tables':{name:payload['tables'][name] for name in ENTITIES}},custody)
        from .pilot_archive_integrity import validate_extended_history
        validate_extended_history(payload,custody)
        return payload
    except Exception:
        raise ValueError('Complete synthetic archive integrity verification failed') from None


@transactional_operation
def export_complete_snapshot(tx,custody):
    tx._auth('backup.export','syn-backup')
    if type(custody) is not SyntheticEvidenceCustody:
        raise PermissionError('Trusted synthetic archive custody required')
    schema_descriptor(tx.connection)
    provenance=_provenance(tx.connection)
    tables={name:sorted([canonical(row) for row in _query(tx.connection,'SELECT * FROM mc_syn.'+name+' WHERE tenant_reference=%s',(tx.tenant,))[0]],key=canonical_bytes) for name in TABLES}
    payload={'format':'syn-pilot-export-v1','dataset':'synthetic','tenant':tx.tenant,'manifest_digest':fingerprint(MANIFEST),
             'migrations':provenance,'tables':tables,'table_digests':{name:fingerprint(rows) for name,rows in tables.items()}}
    archive={'payload':payload,'checksum':fingerprint(payload),'proof':custody.seal(payload)}
    validate_complete_archive(archive,custody)
    return archive


def _restore_row(tx,name,row):
    columns=TABLES[name]['columns']
    converted={key:(datetime.fromisoformat(value) if columns[key]['type']=='timestamptz' and value is not None else value) for key,value in row.items()}
    values=[json_value(value) if columns[key]['type']=='jsonb' else value for key,value in converted.items()]
    markers=['%s::jsonb' if columns[key]['type']=='jsonb' else '%s' for key in converted]
    _query(tx.connection,'INSERT INTO mc_syn.'+name+' ('+','.join(converted)+') VALUES ('+','.join(markers)+')',tuple(values))


def json_value(value):
    return canonical_bytes(value).decode()


@transactional_operation
def restore_complete_snapshot(tx,archive,custody):
    actor,_=tx._auth('backup.restore','syn-backup',context=False)
    payload=validate_complete_archive(archive,custody)
    if payload['tenant']!=tx.tenant: raise PermissionError('Cross-tenant complete restore forbidden')
    schema_descriptor(tx.connection);_provenance(tx.connection)
    if any(_query(tx.connection,'SELECT 1 FROM mc_syn.'+name+' WHERE tenant_reference=%s LIMIT 1',(tx.tenant,))[0] for name in TABLES):
        raise ValueError('Complete restore requires an empty tenant; overwrite/merge forbidden')
    for name in INSERT_ORDER:
        rows=payload['tables'][name]
        if name=='routing_records': rows=sorted(rows,key=lambda row:(row['kind'],row['reference'],row['revision']))
        elif name=='routing_events': rows=sorted(rows,key=lambda row:(row['intake_reference'],row['sequence']))
        elif name=='pilot_proposals': rows=sorted(rows,key=lambda row:(row['journey_reference'],row['event_reference'],row['revision']))
        elif name=='pilot_events': rows=sorted(rows,key=lambda row:(row['journey_reference'],row['sequence']))
        elif name in ('registry_revisions','packet_revisions'): rows=sorted(rows,key=lambda row:row['revision'])
        elif name=='journey_events': rows=sorted(rows,key=lambda row:row['sequence'])
        for row in rows: _restore_row(tx,name,row)
    tx._auth('backup.restore','syn-backup')
    # All source audit records are preserved; this is one additional restore decision.
    tx._audit('backup.restore','syn-backup',actor)


def write_complete_archive(path,archive,custody):
    validate_complete_archive(archive,custody)
    target=Path(path)
    fd,name=tempfile.mkstemp(prefix='.syn-pilot-export-',dir=target.parent)
    temporary=Path(name)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(canonical_bytes(archive));handle.flush();os.fsync(handle.fileno())
        os.link(temporary,target,follow_symlinks=False)
        directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally: temporary.unlink(missing_ok=True)


def read_complete_archive(path,custody):
    archive=strict_json_loads(Path(path).read_text())
    validate_complete_archive(archive,custody)
    return archive

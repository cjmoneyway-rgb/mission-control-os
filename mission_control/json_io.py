"""Strict JSON for every application input boundary, including nested objects."""
import json


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError('Nonfinite JSON constant')


def strict_json_loads(value):
    return json.loads(value, object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)

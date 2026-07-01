from __future__ import annotations

import typing as t
from collections.abc import Callable, Mapping

DOCUMENTATION = r"""
name: older_than
short_description: Whether a timestamp is older than a given age
description:
  - Compares an epoch timestamp (such as C(stat.mtime)) against another epoch
    timestamp (such as C(ansible_facts["date_time"]["epoch"])), and returns
    whether the difference exceeds a threshold, in seconds.
options:
  _input:
    description: Epoch timestamp to check, such as a file's C(mtime).
    type: float
    required: true
  now:
    description: Epoch timestamp to compare against, such as the current time.
    type: float
    required: true
  seconds:
    description: Age threshold, in seconds.
    type: int
    required: true
"""

EXAMPLES = r"""
- name: Re-sync if the tree is more than a day old
  ansible.builtin.command: emerge --sync
  when: sync_timestamp.stat.mtime is older_than(ansible_facts["date_time"]["epoch"], 86400)
"""


def older_than(mtime: t.Any, now: t.Any, seconds: t.Any) -> bool:
    return (int(now) - int(mtime)) > int(seconds)


class TestModule:
    def tests(self) -> Mapping[str, Callable[[t.Any, t.Any, t.Any], bool]]:
        return {"older_than": older_than}
